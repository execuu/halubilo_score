import re
import pytest
from app import create_app, db, User, Team, Activity

@pytest.fixture
def app(tmp_path):
    application = create_app({'TESTING': True, 'SECRET_KEY': 'test-secret-' * 8,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "scoresheet.db"}',
        'UPLOAD_FOLDER': str(tmp_path / 'uploads'), 'SQLITE_WAL': False, 'HTTPS_ONLY': False})
    result = application.test_cli_runner().invoke(args=['migrate'])
    assert result.exit_code == 0, result.output
    with application.app_context():
        activities = [Activity(name='Run', max_score=100), Activity(name='Puzzle', max_score=50)]
        db.session.add_all(activities + [Team(name='Alpha'), Team(name='Beta'), Team(name='Gamma')])
        db.session.flush()
        for username, role, activity_id in [('admin', 'admin', None), ('head', 'user', activities[0].id), ('other', 'user', activities[1].id), ('unassigned', 'user', None)]:
            user = User(username=username, email=username+'@example.com', role=role, activity_id=activity_id)
            user.set_password('fixture-password-123')
            db.session.add(user)
        db.session.commit()
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()

@pytest.fixture
def client(app):
    return app.test_client()

def csrf(client, path='/login'):
    response = client.get(path)
    assert response.status_code == 200, response.data
    return re.search(r'name="csrf_token" value="([^"]+)"', response.text).group(1)

def login(client, username='admin'):
    result = client.post('/login', data={'csrf_token': csrf(client), 'username': username, 'password': 'fixture-password-123'})
    assert result.status_code == 302, result.data

def post(client, path, data=None, token_path='/scores'):
    return client.post(path, data={'csrf_token': csrf(client, token_path), **(data or {})})
