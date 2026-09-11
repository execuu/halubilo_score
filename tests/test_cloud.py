import io
import zipfile
from urllib.error import HTTPError

import pytest
from PIL import Image
from sqlalchemy import select, text

from app import create_app, db, Team
from conftest import login, post
from scripts.restore import restore
import storage_backend


def test_remote_images_survive_new_app_and_restore_to_lan(app, client, monkeypatch, tmp_path):
    objects = {}
    requests = []

    def transport(request, timeout):
        assert request.headers['Authorization'] == 'Bearer server-secret-never-public'
        assert request.headers['Apikey'] == 'server-secret-never-public'
        assert timeout == 15
        requests.append((request.method, request.full_url))
        name = request.full_url.rsplit('/', 1)[1]
        if request.method == 'POST':
            assert name not in objects
            objects[name] = request.data
            return io.BytesIO(b'{}')
        return io.BytesIO(objects[name])

    monkeypatch.setattr(storage_backend, 'urlopen', transport)
    app.config.update(STORAGE_BACKEND='supabase', SUPABASE_URL='https://fixture.supabase.co',
                      SUPABASE_SERVICE_ROLE_KEY='server-secret-never-public')
    login(client)
    picture = io.BytesIO()
    Image.new('RGB', (50, 50), 'blue').save(picture, 'PNG')
    picture.seek(0)
    assert post(client, '/teams', {'name': 'Cloud image', 'image': (picture, 'team.png')}, token_path='/teams').status_code == 302
    with app.app_context():
        filename = db.session.scalar(select(Team.image_filename).where(Team.name == 'Cloud image'))
    # A brand-new process configuration with no local image files still serves it.
    fresh = create_app(dict(app.config, UPLOAD_FOLDER=str(tmp_path / 'empty-disk')))
    response = fresh.test_client().get('/uploads/' + filename)
    assert response.status_code == 200 and response.data == objects[filename]
    assert fresh.test_client().get('/uploads/' + 'f' * 32 + '.jpg').status_code == 404
    assert not (tmp_path / 'empty-disk').exists()
    assert requests[0][1] == 'https://fixture.supabase.co/storage/v1/object/team-images/' + filename
    assert requests[1][1] == 'https://fixture.supabase.co/storage/v1/object/authenticated/team-images/' + filename
    backup = post(client, '/admin/backup')
    assert backup.status_code == 200
    destination = tmp_path / 'lan-recovery'
    restore(io.BytesIO(backup.data), destination)
    assert (destination / 'uploads' / filename).read_bytes() == objects[filename]
    with zipfile.ZipFile(io.BytesIO(backup.data)) as archive:
        assert all(b'server-secret-never-public' not in archive.read(name) for name in archive.namelist())


def test_storage_failure_does_not_save_team_or_leak_provider_error(app, client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise HTTPError('https://fixture.supabase.co', 403, 'sensitive provider details', {}, None)
    monkeypatch.setattr(storage_backend, 'urlopen', unavailable)
    app.config.update(STORAGE_BACKEND='supabase', SUPABASE_URL='https://fixture.supabase.co',
                      SUPABASE_SERVICE_ROLE_KEY='private-key')
    login(client)
    picture = io.BytesIO()
    Image.new('RGB', (10, 10)).save(picture, 'PNG'); picture.seek(0)
    response = post(client, '/teams', {'name': 'Failed upload', 'image': (picture, 'team.png')}, token_path='/teams')
    assert response.status_code == 503
    assert 'sensitive provider details' not in response.text and 'private-key' not in response.text
    with app.app_context():
        assert db.session.scalar(select(Team.id).where(Team.name == 'Failed upload')) is None


def test_proxy_https_and_spoofing_is_opt_in(app):
    secure = create_app(dict(app.config, HTTPS_ONLY=True, TRUST_PROXY=True, SESSION_COOKIE_SECURE=True))
    response = secure.test_client().get('/login', headers={'X-Forwarded-Proto': 'https'})
    assert response.status_code == 200
    assert 'Secure;' in response.headers['Set-Cookie']
    direct = create_app(dict(app.config, HTTPS_ONLY=True, TRUST_PROXY=False))
    assert direct.test_client().get('/login', headers={'X-Forwarded-Proto': 'https'}).status_code == 400


def test_render_refuses_ephemeral_database(app, monkeypatch):
    monkeypatch.setenv('RENDER', 'true')
    with pytest.raises(RuntimeError, match='Render requires'):
        create_app(dict(app.config, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', STORAGE_BACKEND='local'))


def test_postgres_schema_is_private_and_migration_repeat_safe(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL-specific access boundary')
        before = db.session.query(Team).count()
        assert db.session.scalar(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='score'")) == 0
        assert db.session.scalar(text("SELECT COUNT(*) FROM information_schema.role_table_grants WHERE table_schema='halubilo' AND grantee='PUBLIC'")) == 0
        db.session.remove()
    result = app.test_cli_runner().invoke(args=['migrate'])
    assert result.exit_code == 0 and 'no changes' in result.output
    with app.app_context():
        assert db.session.query(Team).count() == before
        with pytest.raises(Exception, match='append-only'):
            db.session.execute(text('TRUNCATE audit'))
        db.session.rollback()
