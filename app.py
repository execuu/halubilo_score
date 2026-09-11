"""Halubilo: a single-event, transactionally recorded team scoresheet."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
import time
import warnings
import zipfile
from contextlib import closing
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlsplit

import click
from dotenv import load_dotenv
from email_validator import validate_email, EmailNotValidError
from flask import Flask, abort, current_app, flash, g, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import create_engine, event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from storage_backend import StorageError, put_image, get_image, cleanup_image

ROOT = Path(__file__).resolve().parent
SCHEMA_VERSION = 1
RELEASE = '1.1.1'
db = SQLAlchemy()
csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = 'login'


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.id', ondelete='RESTRICT'), index=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    auth_version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    activity = db.relationship('Activity')
    __table_args__ = (db.CheckConstraint("role IN ('admin', 'user')"),)

    @property
    def is_active(self):
        return self.enabled

    def get_id(self):
        return f'{self.id}:{self.auth_version}'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        self.auth_version = (self.auth_version or 0) + 1

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    image_filename = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=now)


class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False, default='')
    max_score = db.Column(db.Integer, nullable=False, default=100)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    __table_args__ = (db.CheckConstraint('max_score BETWEEN 1 AND 1000'),)


class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id', ondelete='RESTRICT'), nullable=False)
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.id', ondelete='RESTRICT'), nullable=False, index=True)
    score = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text, nullable=False, default='')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='RESTRICT'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=now)
    version = db.Column(db.Integer, nullable=False, default=1)
    team = db.relationship('Team', lazy='joined')
    activity = db.relationship('Activity', lazy='joined')
    author = db.relationship('User', lazy='joined')
    __table_args__ = (db.UniqueConstraint('team_id', 'activity_id', name='one_score_per_activity'), db.CheckConstraint('score >= 0'), {'sqlite_autoincrement': True})


class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(80), nullable=False)
    entity = db.Column(db.String(100), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    before = db.Column(db.JSON)
    after = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, default=now, index=True)


class EventState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scoring_open = db.Column(db.Boolean, nullable=False, default=True)
    revision = db.Column(db.Integer, nullable=False, default=1)
    __table_args__ = (db.CheckConstraint('id = 1'),)


class SchemaVersion(db.Model):
    version = db.Column(db.Integer, primary_key=True)


class LoginAttempt(db.Model):
    key = db.Column(db.String(64), primary_key=True)
    count = db.Column(db.Integer, nullable=False)
    expires = db.Column(db.Integer, nullable=False, index=True)


@login_manager.user_loader
def load_user(identifier):
    try:
        user_id, auth_version = map(int, identifier.split(':'))
    except (ValueError, AttributeError):
        return None
    user = db.session.get(User, user_id)
    return user if user and user.enabled and user.auth_version == auth_version else None


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != 'admin':
            abort(403)
        return fn(*args, **kwargs)
    return wrapped


def audit(action, entity, reason, before=None, after=None, actor=None):
    db.session.add(Audit(actor=actor or current_user.username, action=action, entity=str(entity), reason=reason, before=before, after=after))


def value(name, limit=100, required=True):
    result = request.form.get(name, '').strip()
    if (required and not result) or len(result) > limit:
        abort(400, f'{name.replace("_", " ").capitalize()} is required and must be at most {limit} characters.')
    return result


def integer(name, minimum=0, maximum=2147483647):
    raw = request.form.get(name, '')
    try:
        if not raw or not raw.isascii() or not raw.isdigit():
            raise ValueError
        result = int(raw)
        if not minimum <= result <= maximum:
            raise ValueError
        return result
    except ValueError:
        abort(400, f'{name.replace("_", " ").capitalize()} must be a whole number from {minimum} to {maximum}.')


def state():
    result = db.session.get(EventState, 1)
    if result is None:
        abort(503, 'Database is not initialized. Run the migration command.')
    return result


def changed():
    state().revision += 1


def score_snapshot(score):
    return dict(id=score.id, team_id=score.team_id, activity_id=score.activity_id, score=score.score, notes=score.notes, version=score.version, created_by=score.created_by)


def leaderboard():
    # One query regardless of team count; missing scores remain distinguishable.
    rows = db.session.execute(select(Team.id, Team.name, Team.image_filename,
        func.coalesce(func.sum(Score.score), 0).label('total_score'),
        func.count(Score.id).label('activities_completed')).outerjoin(Score, Team.id == Score.team_id)
        .group_by(Team.id).order_by(text('total_score DESC'), func.lower(Team.name), Team.id)).mappings().all()
    output, previous, rank = [], None, 0
    for index, row in enumerate(rows, 1):
        item = dict(row)
        if item['total_score'] != previous:
            rank = index
        previous = item['total_score']
        item['rank'] = rank
        output.append(item)
    return output


def image_upload(upload):
    if not upload or not upload.filename:
        return None
    raw = upload.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        abort(400, 'Team images must be 2 MiB or smaller.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in {'JPEG', 'PNG', 'GIF', 'WEBP'}:
                    abort(400, 'Use a JPEG, PNG, GIF, or WebP image.')
                if source.width * source.height > 16_000_000:
                    abort(400, 'Image dimensions are too large.')
                image = ImageOps.exif_transpose(source).convert('RGB')
                image.thumbnail((512, 512))
                name = secrets.token_hex(16) + '.jpg'
                encoded = io.BytesIO()
                image.save(encoded, 'JPEG', quality=85, optimize=True)
                put_image(name, encoded.getvalue())
                g.new_uploads.append(name)
                return name
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        abort(400, 'The uploaded file is not a valid supported image.')


def make_backup():
    """Caller holds the event write lock; export a portable SQLite snapshot."""
    filename = db.engine.url.database
    if filename == ':memory:':
        abort(400, 'Backups require a file-backed database.')
    with tempfile.TemporaryDirectory(prefix='halubilo-backup-') as folder:
        snapshot = Path(folder) / 'scoresheet.db'
        if db.engine.dialect.name == 'sqlite':
            with closing(sqlite3.connect(filename)) as source, closing(sqlite3.connect(snapshot)) as dest:
                source.backup(dest)
        else:
            # Same typed tables and constraints as the LAN release. The event lock
            # keeps all application writes ordered while the snapshot is copied.
            with closing(sqlite3.connect(snapshot)) as connection:
                connection.executescript((ROOT / 'migrations' / '001_initial.sql').read_text())
            target_engine = create_engine(f'sqlite:///{snapshot}')
            try:
                with target_engine.begin() as target:
                    target.execute(text('DELETE FROM schema_version'))
                    target.execute(text('DELETE FROM event_state'))
                    for table in db.metadata.sorted_tables:
                        rows = [dict(row) for row in db.session.execute(select(table)).mappings()]
                        if rows:
                            target.execute(table.insert(), rows)
                    # Preserve IDs already consumed by reset/deleted scores so a
                    # LAN recovery cannot reuse identifiers referenced by history.
                    sequence = db.session.execute(text('SELECT last_value, is_called FROM score_id_seq')).one()
                    high_water = sequence.last_value if sequence.is_called else 0
                    high_water = max(high_water, target.scalar(select(func.coalesce(func.max(Score.id), 0))))
                    target.execute(text("DELETE FROM sqlite_sequence WHERE name='score'"))
                    target.execute(text("INSERT INTO sqlite_sequence(name, seq) VALUES ('score', :value)"), {'value': high_water})
            finally:
                target_engine.dispose()
        image_names = db.session.scalars(select(Team.image_filename).where(Team.image_filename.is_not(None))).all()
        snapshot_time = now().isoformat() + 'Z'
        files = {'scoresheet.db': snapshot.read_bytes()}
        # Referenced images have immutable names and are never deleted by the
        # app. Release the writer lock before potentially slow object downloads.
        db.session.rollback()
        for name in image_names:
            if Path(name).name != name:
                abort(500, 'Invalid stored image path.')
            files[f'uploads/{name}'] = get_image(name)
        manifest = {'release': RELEASE, 'schema': SCHEMA_VERSION, 'created_at': snapshot_time,
                    'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
            archive.writestr('manifest.json', json.dumps(manifest, indent=2))
        output.seek(0)
        return output


def create_app(config=None):
    load_dotenv(ROOT / '.env')
    app = Flask(__name__)
    data_dir = ROOT / 'instance'
    production = os.environ.get('APP_ENV', 'lan') == 'production'
    app.config.update(
        SECRET_KEY=os.environ.get('SECRET_KEY'),
        SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', f'sqlite:///{data_dir / "scoresheet.db"}'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={'connect_args': {'timeout': 10}},
        UPLOAD_FOLDER=os.environ.get('UPLOAD_FOLDER', str(data_dir / 'uploads')),
        EVENT_NAME=os.environ.get('EVENT_NAME', 'Halubilo'),
        STORAGE_BACKEND=os.environ.get('STORAGE_BACKEND', 'local'),
        SUPABASE_URL=os.environ.get('SUPABASE_URL', ''),
        SUPABASE_SERVICE_ROLE_KEY=os.environ.get('SUPABASE_SERVICE_ROLE_KEY', ''),
        SUPABASE_STORAGE_BUCKET=os.environ.get('SUPABASE_STORAGE_BUCKET', 'team-images'),
        TRUST_PROXY=os.environ.get('TRUST_PROXY', '0') == '1',
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=128 * 1024,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=production,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        WTF_CSRF_TIME_LIMIT=12 * 60 * 60,
        HTTPS_ONLY=os.environ.get('HTTPS_ONLY', '1' if production else '0') == '1',
        SQLITE_WAL=os.environ.get('SQLITE_WAL', '0') == '1',
        SEND_FILE_MAX_AGE_DEFAULT=3600,
    )
    if config:
        app.config.update(config)
    if not app.config['SECRET_KEY'] or len(app.config['SECRET_KEY']) < 32:
        raise RuntimeError('Set a unique SECRET_KEY of at least 32 characters (make setup).')
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    for prefix in ('postgres://', 'postgresql://'):
        if uri.startswith(prefix):
            uri = 'postgresql+psycopg://' + uri[len(prefix):]
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
    postgres = uri.startswith('postgresql+psycopg://')
    if postgres:
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True, 'pool_size': 4, 'max_overflow': 0, 'pool_timeout': 10,
            'connect_args': {'connect_timeout': 10, 'prepare_threshold': None},
        }
    elif not uri.startswith('sqlite:'):
        raise RuntimeError('Use SQLite or PostgreSQL with the psycopg driver.')
    if app.config['STORAGE_BACKEND'] not in {'local', 'supabase'}:
        raise RuntimeError('STORAGE_BACKEND must be local or supabase.')
    if app.config['STORAGE_BACKEND'] == 'supabase':
        if not app.config['SUPABASE_URL'].startswith('https://') or not app.config['SUPABASE_SERVICE_ROLE_KEY']:
            raise RuntimeError('Supabase storage requires an HTTPS SUPABASE_URL and a server-only service role key.')
        import re
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', app.config['SUPABASE_STORAGE_BUCKET']):
            raise RuntimeError('Invalid Supabase bucket name.')
    else:
        Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)
    if os.environ.get('RENDER') == 'true' and (not postgres or app.config['STORAGE_BACKEND'] != 'supabase'):
        raise RuntimeError('Render requires PostgreSQL and Supabase storage; local files are ephemeral.')
    if app.config['TRUST_PROXY']:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    with app.app_context():
        if not postgres and db.engine.url.database != ':memory:':
            Path(db.engine.url.database).parent.mkdir(parents=True, exist_ok=True)
        @event.listens_for(db.engine, 'connect')
        def sqlite_connection(connection, _):
            if postgres:
                connection.autocommit = True
                with connection.cursor() as cursor:
                    cursor.execute('SET search_path TO halubilo')
                    cursor.execute("SET lock_timeout TO '10s'")
                    cursor.execute("SET statement_timeout TO '25s'")
                connection.autocommit = False
            else:
                cursor = connection.cursor()
                cursor.execute('PRAGMA foreign_keys=ON')
                cursor.execute('PRAGMA busy_timeout=10000')
                cursor.close()

    @app.before_request
    def prepare_request():
        g.new_uploads = []
        g.committed = False
        if app.config['HTTPS_ONLY'] and not request.is_secure and request.path not in {'/healthz', '/livez'}:
            abort(400, 'HTTPS is required.')
        if request.method == 'POST':
            # Lock before authorization reads: corrections, role changes, closure
            # and backup snapshots share one serial order on either database.
            begin_write()

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
        if app.config['HTTPS_ONLY']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        if not request.path.startswith('/static/') and not request.path.startswith('/uploads/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.teardown_request
    def cleanup(_error):
        db.session.rollback()
        if not getattr(g, 'committed', False):
            for filename in getattr(g, 'new_uploads', []):
                cleanup_image(filename)

    @app.errorhandler(StorageError)
    def storage_error(error):
        return render_template('error.html', message=str(error)), 503

    @app.errorhandler(IntegrityError)
    def integrity_error(error):
        db.session.rollback()
        app.logger.warning('Constraint rejected %s %s', request.method, request.path)
        return render_template('error.html', message='That record conflicts with an existing or referenced record. Refresh and check before retrying.'), 409

    @app.errorhandler(OperationalError)
    def database_error(error):
        db.session.rollback()
        app.logger.exception('Database operation failed')
        return render_template('error.html', message='Database temporarily unavailable. Check the current score before retrying; contact the administrator if this continues.'), 503, {'Retry-After': '3'}

    @app.errorhandler(HTTPException)
    def http_error(error):
        return render_template('error.html', message=error.description), error.code

    @app.errorhandler(500)
    def server_error(error):
        return render_template('error.html', message='The request could not be completed. Contact the administrator and check the current record before retrying.'), 500

    @app.context_processor
    def template_context():
        return {'event_name': app.config['EVENT_NAME'], 'release': RELEASE}

    @app.template_filter('manila')
    def manila(value):
        return (value + timedelta(hours=8)).strftime('%b %d, %Y %I:%M %p') if value else ''

    @app.get('/livez')
    def livez():
        return jsonify(status='ok', release=RELEASE)

    @app.get('/healthz')
    def healthz():
        try:
            version = db.session.scalar(select(SchemaVersion.version))
            ready = version == SCHEMA_VERSION and db.session.get(EventState, 1) is not None
        except Exception:
            db.session.rollback()
            ready = False
        return jsonify(status='ok' if ready else 'not-ready', release=RELEASE), 200 if ready else 503

    @app.get('/')
    def index():
        return render_template('index.html', standings=leaderboard(), activities=db.session.scalars(select(Activity).order_by(Activity.name)).all(), event_state=state())

    @app.get('/api/leaderboard')
    def api_leaderboard():
        response = jsonify(leaderboard())
        response.headers['X-Scoring-Open'] = '1' if state().scoring_open else '0'
        return response

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            username = value('username', 80)
            password = value('password', 1024)
            timestamp = int(time.time())
            db.session.execute(db.delete(LoginAttempt).where(LoginAttempt.expires < timestamp))
            keys = [('ip:' + (request.remote_addr or 'unknown'), 50), ('user:' + username.casefold(), 10)]
            attempts = []
            for raw_key, limit in keys:
                key = hashlib.sha256(raw_key.encode()).hexdigest()
                attempt = db.session.get(LoginAttempt, key)
                if attempt is None:
                    attempt = LoginAttempt(key=key, count=0, expires=timestamp + 900)
                    db.session.add(attempt)
                if attempt.count >= limit:
                    commit()
                    abort(429, 'Too many login attempts. Wait 15 minutes before trying again.')
                attempts.append(attempt)
            user = db.session.scalar(select(User).where(User.username == username))
            if user and user.enabled and user.check_password(password):
                for attempt in attempts:
                    if attempt.key == hashlib.sha256(('user:' + username.casefold()).encode()).hexdigest():
                        attempt.count = 0
                login_user(user)
                commit()
                next_page = request.args.get('next', '')
                parts = urlsplit(next_page)
                safe = next_page.startswith('/') and not next_page.startswith('//') and '\\' not in next_page and not parts.netloc and not parts.scheme and not any(ord(c) < 32 for c in next_page)
                return redirect(next_page if safe else url_for('dashboard'))
            for attempt in attempts:
                attempt.count += 1
            commit()
            flash('Invalid username or password.', 'error')
            return render_template('login.html'), 401
        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        abort(404)

    @app.post('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('index'))

    @app.get('/dashboard')
    @login_required
    def dashboard():
        return redirect(url_for('admin_dashboard' if current_user.role == 'admin' else 'user_dashboard'))

    @app.get('/user/dashboard')
    @login_required
    def user_dashboard():
        return redirect(url_for('scores'))

    @app.get('/admin/dashboard')
    @admin_required
    def admin_dashboard():
        counts = {name: db.session.scalar(select(func.count()).select_from(model)) for name, model in [('teams', Team), ('activities', Activity), ('scores', Score), ('users', User)]}
        return render_template('admin_dashboard.html', counts=counts, standings=leaderboard(), event_state=state(), activities=db.session.scalars(select(Activity)).all())

    @app.route('/teams', methods=['GET', 'POST'])
    @admin_required
    def teams():
        if request.method == 'POST':
            upload = request.files.get('csv_file')
            if upload and upload.filename:
                try:
                    raw = upload.read(512 * 1024 + 1)
                    if len(raw) > 512 * 1024:
                        abort(400, 'CSV must be 512 KiB or smaller.')
                    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), strict=True)
                    if reader.fieldnames != ['Team Name']:
                        abort(400, 'CSV must have exactly one column named Team Name.')
                    names = []
                    for row in reader:
                        if None in row or row.get('Team Name') is None:
                            abort(400, 'Each CSV row must contain one team name.')
                        name = row['Team Name'].strip()
                        if not name or len(name) > 100:
                            abort(400, 'Every team name must contain 1–100 characters.')
                        names.append(name)
                        if len(names) > 1000:
                            abort(400, 'Import at most 1000 teams at a time.')
                    if not names:
                        abort(400, 'CSV contains no teams.')
                    existing = set(db.session.scalars(select(Team.name)))
                    added = sorted(set(names) - existing)
                    db.session.add_all(Team(name=name) for name in added)
                    audit('teams.import', 'teams', 'CSV import', after={'added': added, 'skipped': len(names) - len(added)})
                    changed()
                    commit()
                    flash(f'Imported {len(added)} teams; skipped {len(names) - len(added)} duplicates.', 'success')
                except (UnicodeError, csv.Error):
                    abort(400, 'CSV must be valid UTF-8 with one Team Name column.')
            else:
                team = Team(name=value('name'), image_filename=image_upload(request.files.get('image')))
                db.session.add(team)
                db.session.flush()
                audit('team.create', f'team:{team.id}', 'Team setup', after={'name': team.name})
                changed()
                commit()
                flash('Team added.', 'success')
            return redirect(url_for('teams'))
        return render_template('teams.html', teams=db.session.scalars(select(Team).order_by(Team.name)).all())

    @app.route('/teams/<int:team_id>/edit', methods=['GET', 'POST'])
    @admin_required
    def edit_team(team_id):
        team = db.get_or_404(Team, team_id)
        if request.method == 'POST':
            before = {'name': team.name, 'image_filename': team.image_filename}
            team.name = value('name')
            image = image_upload(request.files.get('image'))
            if image:
                team.image_filename = image
            audit('team.edit', f'team:{team.id}', value('reason', 1000), before, {'name': team.name, 'image_filename': team.image_filename})
            changed()
            commit()
            return redirect(url_for('teams'))
        return render_template('edit_team.html', team=team)

    @app.post('/teams/<int:team_id>/delete')
    @admin_required
    def delete_team(team_id):
        team = db.get_or_404(Team, team_id)
        if db.session.scalar(select(Score.id).where(Score.team_id == team.id).limit(1)):
            abort(409, 'A team with recorded scores cannot be deleted.')
        audit('team.delete', f'team:{team.id}', value('reason', 1000), {'name': team.name})
        db.session.delete(team)
        changed()
        commit()
        return redirect(url_for('teams'))

    @app.route('/activities', methods=['GET', 'POST'])
    @admin_required
    def activities():
        if request.method == 'POST':
            activity = Activity(name=value('name'), description=value('description', 2000, False), max_score=integer('max_score', 1, 1000))
            db.session.add(activity)
            db.session.flush()
            audit('activity.create', f'activity:{activity.id}', 'Activity setup', after={'name': activity.name, 'max_score': activity.max_score})
            changed()
            commit()
            return redirect(url_for('activities'))
        return render_template('activities.html', activities=db.session.scalars(select(Activity).order_by(Activity.name)).all())

    @app.route('/activities/<int:activity_id>/edit', methods=['GET', 'POST'])
    @admin_required
    def edit_activity(activity_id):
        activity = db.get_or_404(Activity, activity_id)
        if request.method == 'POST':
            maximum = integer('max_score', 1, 1000)
            highest = db.session.scalar(select(func.max(Score.score)).where(Score.activity_id == activity.id))
            if highest is not None and maximum < highest:
                abort(409, 'The maximum cannot be lower than an existing score.')
            before = {'name': activity.name, 'max_score': activity.max_score, 'description': activity.description}
            activity.name, activity.max_score = value('name'), maximum
            activity.description = value('description', 2000, False)
            audit('activity.edit', f'activity:{activity.id}', value('reason', 1000), before, {'name': activity.name, 'max_score': maximum, 'description': activity.description})
            changed()
            commit()
            return redirect(url_for('activities'))
        return render_template('edit_activity.html', activity=activity)

    @app.post('/activities/<int:activity_id>/delete')
    @admin_required
    def delete_activity(activity_id):
        activity = db.get_or_404(Activity, activity_id)
        if db.session.scalar(select(Score.id).where(Score.activity_id == activity.id).limit(1)) or db.session.scalar(select(User.id).where(User.activity_id == activity.id).limit(1)):
            abort(409, 'An activity with scores or assigned users cannot be deleted.')
        audit('activity.delete', f'activity:{activity.id}', value('reason', 1000), {'name': activity.name})
        db.session.delete(activity)
        changed()
        commit()
        return redirect(url_for('activities'))

    @app.route('/admin/users', methods=['GET', 'POST'])
    @admin_required
    def admin_users():
        if request.method == 'POST':
            password = value('password', 1024)
            if len(password) < 12:
                abort(400, 'Use a password of at least 12 characters.')
            try:
                email = validate_email(value('email', 120), check_deliverability=False).normalized
            except EmailNotValidError:
                abort(400, 'Enter a valid email address.')
            activity = db.get_or_404(Activity, integer('activity_id', 1))
            user = User(username=value('username', 80), email=email, role='user', activity_id=activity.id)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            audit('user.create', f'user:{user.id}', 'Activity-head setup', after={'username': user.username, 'activity_id': activity.id})
            commit()
            flash('Activity-head account created.', 'success')
            return redirect(url_for('admin_users'))
        return render_template('admin_users.html', users=db.session.scalars(select(User).options(db.joinedload(User.activity)).order_by(User.username)).all(), activities=db.session.scalars(select(Activity).order_by(Activity.name)).all())

    @app.post('/admin/users/<int:user_id>/update')
    @admin_required
    def update_user(user_id):
        user = db.get_or_404(User, user_id)
        reason = value('reason', 1000)
        before = {'enabled': user.enabled, 'role': user.role, 'activity_id': user.activity_id}
        role = value('role', 20)
        if role not in {'admin', 'user'}:
            abort(400, 'Invalid role.')
        enabled = request.form.get('enabled') == '1'
        if user.id == current_user.id and (not enabled or role != 'admin'):
            abort(409, 'You cannot disable or demote your own administrator account.')
        user.role, user.enabled = role, enabled
        activity_id = request.form.get('activity_id')
        user.activity_id = db.get_or_404(Activity, integer('activity_id', 1)).id if activity_id else None
        if enabled and role == 'user' and user.activity_id is None:
            abort(400, 'An enabled activity head needs an activity assignment.')
        password = value('password', 1024, False)
        if password:
            if len(password) < 12:
                abort(400, 'Use a password of at least 12 characters.')
            user.set_password(password)
        else:
            user.auth_version += 1
        audit('user.update', f'user:{user.id}', reason, before, {'enabled': enabled, 'role': role, 'activity_id': user.activity_id, 'password_reset': bool(password)})
        if user.id == current_user.id:
            login_user(user)
        commit()
        return redirect(url_for('admin_users'))

    @app.post('/admin/users/<int:user_id>/delete')
    @admin_required
    def delete_user(user_id):
        user = db.get_or_404(User, user_id)
        if user.id == current_user.id or db.session.scalar(select(Score.id).where(Score.created_by == user.id).limit(1)):
            abort(409, 'This account cannot be deleted. Disable referenced accounts instead.')
        audit('user.delete', f'user:{user.id}', value('reason', 1000), {'username': user.username})
        db.session.delete(user)
        commit()
        return redirect(url_for('admin_users'))

    @app.route('/scores', methods=['GET', 'POST'])
    @login_required
    def scores():
        if request.method == 'POST':
            if not state().scoring_open:
                abort(409, 'Scoring is closed. Ask an administrator to reopen it.')
            if current_user.role != 'admin' and not current_user.activity_id:
                abort(403, 'You need an activity assignment before submitting scores.')
            activity_id = integer('activity_id', 1)
            if current_user.role != 'admin' and activity_id != current_user.activity_id:
                abort(403, 'You can submit only for your assigned activity.')
            activity = db.get_or_404(Activity, activity_id)
            team = db.get_or_404(Team, integer('team_id', 1))
            if db.session.scalar(select(Score.id).where(Score.team_id == team.id, Score.activity_id == activity.id)):
                abort(409, 'A final score is already recorded for this team and activity. An administrator must correct it.')
            score = Score(team_id=team.id, activity_id=activity.id, score=integer('score', 0, activity.max_score), notes=value('notes', 2000, False), created_by=current_user.id)
            db.session.add(score)
            db.session.flush()
            audit('score.submit', f'score:{score.id}', 'Final score submitted', after=score_snapshot(score))
            changed()
            commit()
            flash(f'{team.name}: {score.score} points recorded for {activity.name}.', 'success')
            return redirect(url_for('scores'))
        query = select(Score).order_by(Score.created_at.desc(), Score.id.desc())
        available = select(Activity).order_by(Activity.name)
        if current_user.role != 'admin':
            query = query.where(Score.activity_id == (current_user.activity_id or -1))
            available = available.where(Activity.id == (current_user.activity_id or -1))
        pagination = db.paginate(query, per_page=50, max_per_page=50, error_out=False)
        return render_template('scores.html', pagination=pagination, teams=db.session.scalars(select(Team).order_by(Team.name)).all(), activities=db.session.scalars(available).all(), standings=leaderboard(), event_state=state())

    @app.route('/scores/<int:score_id>/edit', methods=['GET', 'POST'])
    @admin_required
    def edit_score(score_id):
        score = db.get_or_404(Score, score_id)
        if request.method == 'POST':
            if not state().scoring_open:
                abort(409, 'Reopen scoring with a reason before correcting scores.')
            if integer('version', 1) != score.version:
                abort(409, 'This score changed after you opened it. Reload and review the latest value.')
            before = score_snapshot(score)
            score.score = integer('score', 0, score.activity.max_score)
            score.notes = value('notes', 2000, False)
            score.version += 1
            score.updated_at = now()
            audit('score.correct', f'score:{score.id}', value('reason', 1000), before, score_snapshot(score))
            changed()
            commit()
            flash('Correction recorded with its history.', 'success')
            return redirect(url_for('scores'))
        return render_template('edit_score.html', score=score)

    @app.post('/scores/<int:score_id>/delete')
    @admin_required
    def delete_score(score_id):
        score = db.get_or_404(Score, score_id)
        if not state().scoring_open:
            abort(409, 'Reopen scoring before deleting a score.')
        if integer('version', 1) != score.version:
            abort(409, 'The score changed. Reload before deleting it.')
        if value('confirmation') != 'DELETE':
            abort(400, 'Type DELETE to confirm.')
        audit('score.delete', f'score:{score.id}', value('reason', 1000), score_snapshot(score))
        db.session.delete(score)
        changed()
        commit()
        return redirect(url_for('scores'))

    @app.post('/admin/reset-scores')
    @admin_required
    def reset_scores():
        if state().scoring_open:
            abort(409, 'Close scoring and download a backup before resetting scores.')
        if value('confirmation') != 'RESET ALL SCORES':
            abort(400, 'Type RESET ALL SCORES to confirm.')
        reason = value('reason', 1000)
        all_scores = db.session.scalars(select(Score)).unique().all()
        for score in all_scores:
            audit('score.reset', f'score:{score.id}', reason, score_snapshot(score))
            db.session.delete(score)
        audit('event.reset', 'event:1', reason, {'score_count': len(all_scores)}, {'score_count': 0})
        changed()
        commit()
        flash('Scores reset. Scoring remains closed; audit history has been retained.', 'success')
        return redirect(url_for('admin_dashboard'))

    @app.post('/admin/scoring')
    @admin_required
    def scoring_state():
        event_state = state()
        if integer('revision', 1) != event_state.revision:
            abort(409, 'Event data changed. Reload before changing scoring status.')
        opening = request.form.get('scoring_open') == '1'
        if request.form.get('scoring_open') not in {'0', '1'}:
            abort(400, 'Invalid scoring status.')
        before = {'scoring_open': event_state.scoring_open}
        event_state.scoring_open = opening
        changed()
        audit('event.open' if opening else 'event.close', 'event:1', value('reason', 1000), before, {'scoring_open': opening})
        commit()
        return redirect(url_for('admin_dashboard'))

    @app.get('/admin/audit')
    @admin_required
    def audit_history():
        return render_template('audit.html', pagination=db.paginate(select(Audit).order_by(Audit.id.desc()), per_page=50, max_per_page=50, error_out=False))

    @app.post('/admin/backup')
    @admin_required
    def backup_download():
        archive = make_backup()
        begin_write()
        audit('backup.download', 'event:1', 'Consistent database and images exported')
        commit()
        return send_file(archive, mimetype='application/zip', as_attachment=True, download_name=f'halubilo-{now().strftime("%Y%m%dT%H%M%SZ")}.zip')

    @app.get('/reports')
    @admin_required
    def reports():
        activities = db.session.scalars(select(Activity).order_by(Activity.id)).all()
        matrix = {(s.team_id, s.activity_id): s.score for s in db.session.scalars(select(Score)).unique()}
        standings = leaderboard()
        if request.args.get('format') == 'csv':
            output = io.StringIO(newline='')
            writer = csv.writer(output)
            writer.writerow(['Rank', 'Team', *[safe_csv(a.name) for a in activities], 'Total', 'Completed'])
            for item in standings:
                writer.writerow([item['rank'], safe_csv(item['name']), *[matrix.get((item['id'], a.id), '') for a in activities], item['total_score'], item['activities_completed']])
            return output.getvalue(), 200, {'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': 'attachment; filename=standings.csv'}
        groups = [activities[i:i + 8] for i in range(0, len(activities), 8)] or [[]]
        return render_template('reports.html', standings=standings, activities=activities, activity_groups=groups, matrix=matrix, generated=now(), event_state=state())

    @app.get('/uploads/<path:filename>')
    def uploaded_image(filename):
        if app.config['STORAGE_BACKEND'] == 'local':
            return send_from_directory(app.config['UPLOAD_FOLDER'], filename, max_age=86400)
        # Only referenced images are readable; service keys never reach browsers.
        if not db.session.scalar(select(Team.id).where(Team.image_filename == filename)):
            abort(404)
        return send_file(io.BytesIO(get_image(filename)), mimetype='image/jpeg', max_age=86400)

    @app.get('/download/sample-teams-csv')
    @admin_required
    def download_sample_csv():
        return 'Team Name\nTeam Alpha\nTeam Beta\n', 200, {'Content-Type': 'text/csv', 'Content-Disposition': 'attachment; filename=sample-teams.csv'}

    register_cli(app)
    return app


def safe_csv(value):
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value


def commit():
    db.session.commit()
    g.committed = True


def begin_write():
    if db.engine.dialect.name == 'postgresql':
        db.session.execute(text('SELECT pg_advisory_xact_lock(721940113)'))
    else:
        db.session.execute(text('BEGIN IMMEDIATE'))


def register_cli(app):
    @app.cli.command('migrate')
    def migrate():
        """Initialize a fresh event; refuse to modify an unversioned legacy DB."""
        if db.engine.dialect.name == 'postgresql':
            # One transaction makes first startup atomic, even with two deploys.
            with db.engine.begin() as connection:
                connection.execute(text('SELECT pg_advisory_xact_lock(721940113)'))
                connection.execute(text('CREATE SCHEMA IF NOT EXISTS halubilo'))
                connection.execute(text('REVOKE ALL ON SCHEMA halubilo FROM PUBLIC'))
                tables = inspect(connection).get_table_names(schema='halubilo')
                if tables:
                    if 'schema_version' not in tables or connection.scalar(select(SchemaVersion.version)) != SCHEMA_VERSION:
                        raise click.ClickException('Unrecognized database schema. Use a fresh project or review an explicit migration.')
                    click.echo('Schema is current; no changes made.')
                    return
                db.metadata.create_all(connection)
                connection.exec_driver_sql((ROOT / 'migrations' / '001_postgres_triggers.sql').read_text())
                connection.execute(SchemaVersion.__table__.insert().values(version=SCHEMA_VERSION))
                connection.execute(EventState.__table__.insert().values(id=1, scoring_open=True, revision=1))
                connection.execute(text('REVOKE ALL ON ALL TABLES IN SCHEMA halubilo FROM PUBLIC'))
                connection.execute(text('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA halubilo FROM PUBLIC'))
            click.echo('PostgreSQL schema 1 initialized. Create an administrator with admin-create.')
            return
        tables = inspect(db.engine).get_table_names()
        if tables:
            if 'schema_version' not in tables or db.session.scalar(select(SchemaVersion.version)) != SCHEMA_VERSION:
                raise click.ClickException('Unrecognized database schema. Preserve this database; use a fresh event database or review an explicit migration.')
            click.echo('Schema is current; no changes made.')
            return
        with sqlite3.connect(db.engine.url.database) as connection:
            connection.executescript((ROOT / 'migrations' / '001_initial.sql').read_text())
            if app.config['SQLITE_WAL']:
                connection.execute('PRAGMA journal_mode=WAL')
        click.echo('Schema 1 initialized. Create an administrator with admin-create.')

    @app.cli.command('admin-create')
    @click.option('--username', prompt=True)
    @click.option('--email', prompt=True)
    @click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
    def admin_create(username, email, password):
        """Create an administrator without resetting an existing account."""
        if not 1 <= len(username.strip()) <= 80 or len(password) < 12:
            raise click.ClickException('Username must be 1–80 characters; password must be at least 12 characters.')
        try:
            email = validate_email(email, check_deliverability=False).normalized
        except EmailNotValidError as error:
            raise click.ClickException(str(error))
        begin_write()
        existing = db.session.scalar(select(User).where(User.username == username.strip()))
        if existing:
            if existing.role != 'admin':
                raise click.ClickException('Existing account is not an administrator. Use admin-recover with a reason.')
            click.echo('Administrator already exists; password unchanged.')
            return
        user = User(username=username.strip(), email=email, role='admin', enabled=True)
        user.set_password(password)
        db.session.add(user)
        audit('admin.create', f'user:{user.username}', 'Initial operator setup', actor='CLI operator')
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise click.ClickException('Username or email already exists.')
        click.echo('Administrator created.')

    @app.cli.command('admin-recover')
    @click.option('--username', prompt=True)
    @click.option('--reason', prompt=True)
    @click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
    def admin_recover(username, reason, password):
        """Audited password/role recovery; existing browser sessions are revoked."""
        if len(password) < 12 or not reason.strip() or len(reason) > 1000:
            raise click.ClickException('A reason and a password of at least 12 characters are required.')
        begin_write()
        user = db.session.scalar(select(User).where(User.username == username))
        if not user:
            raise click.ClickException('Account not found. Use admin-create for a new account.')
        user.role, user.enabled = 'admin', True
        user.set_password(password)
        db.session.execute(db.delete(LoginAttempt))
        audit('admin.recover', f'user:{user.id}', reason.strip(), actor='CLI operator')
        db.session.commit()
        click.echo('Administrator recovered; previous sessions revoked.')

    @app.cli.command('backup')
    @click.argument('destination', type=click.Path())
    def backup_cli(destination):
        """Write a private, consistent backup archive outside the web root."""
        begin_write()
        archive = make_backup()
        target = Path(destination)
        with target.open('xb') as output:
            os.chmod(target, 0o600)
            output.write(archive.getvalue())
        begin_write()
        audit('backup.create', 'event:1', 'CLI backup', actor='CLI operator')
        db.session.commit()
        click.echo(f'Backup created: {target}')


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=5000, debug=False)
