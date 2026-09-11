#!/usr/bin/env python3
"""Populate ONLY an explicitly designated, empty rehearsal database."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app, db, User, Activity, Team, audit

if os.environ.get('REHEARSAL_ONLY') != '1':
    raise SystemExit('Refusing: set REHEARSAL_ONLY=1 and use a separate rehearsal database.')
password = os.environ.get('REHEARSAL_PASSWORD')
if not password or len(password) < 12:
    raise SystemExit('Set REHEARSAL_PASSWORD (at least 12 characters).')
app = create_app()
with app.app_context():
    if db.session.query(User).count() or db.session.query(Team).count():
        raise SystemExit('Refusing: rehearsal database is not empty.')
    for i in range(1, 21):
        activity = Activity(id=i, name=f'Activity {i:02}', max_score=100)
        db.session.add(activity)
        db.session.flush()
        user = User(username=f'head{i:02}', email=f'head{i:02}@example.com', role='user', activity_id=i)
        user.set_password(password)
        db.session.add(user)
    admin = User(username='rehearsal-admin', email='rehearsal-admin@example.com', role='admin')
    admin.set_password(password)
    db.session.add(admin)
    db.session.add_all(Team(id=i, name=f'Team {i:02}') for i in range(1,31))
    audit('rehearsal.seed', 'event:1', 'Disposable capacity test only', actor='CLI operator')
    db.session.commit()
print('Seeded 30 teams, 20 activities, 20 assigned heads and one rehearsal admin. No scores.')
