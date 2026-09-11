#!/usr/bin/env python3
"""Atomic fresh-schema setup and one-time admin creation before Gunicorn starts."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app, db, User
from sqlalchemy import select

app = create_app()
with app.app_context():
    runner = app.test_cli_runner()
    result = runner.invoke(args=['migrate'])
    if result.exit_code:
        raise SystemExit('Database migration failed; startup refused. Check connectivity and schema version.')
    if not db.session.scalar(select(User.id).where(User.role == 'admin')):
        required = ['INITIAL_ADMIN_USERNAME', 'INITIAL_ADMIN_EMAIL', 'INITIAL_ADMIN_PASSWORD']
        if not all(os.environ.get(key) for key in required):
            raise SystemExit('Fresh deployment requires INITIAL_ADMIN_USERNAME, INITIAL_ADMIN_EMAIL and INITIAL_ADMIN_PASSWORD.')
        db.session.rollback()
        result = runner.invoke(args=['admin-create', '--username', os.environ[required[0]],
                                    '--email', os.environ[required[1]], '--password', os.environ[required[2]]])
        if result.exit_code:
            raise SystemExit('Initial administrator creation failed. Check username, email and password length.')
    db.session.remove()
    db.engine.dispose()
# Initial credential is never logged and is not inherited by worker processes.
os.environ.pop('INITIAL_ADMIN_PASSWORD', None)
os.execvp('gunicorn', ['gunicorn', '--bind', '0.0.0.0:' + os.environ.get('PORT', '8080'),
                     '--workers', '1', '--threads', '4', '--timeout', '120',
                     '--access-logfile', '-', '--error-logfile', '-', 'wsgi:app'])
