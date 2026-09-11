import io
import json
from pathlib import Path
import sqlite3
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError

from app import db, Score, Audit, User, Team, Activity, EventState, create_app
from conftest import login, post, csrf
from scripts.restore import restore


def submit(client, score=50, team=1, activity=1):
    return post(client, '/scores', {'team_id': str(team), 'activity_id': str(activity), 'score': str(score)})

@pytest.mark.parametrize('score,expected', [(0,302),(100,302),(-1,400),(101,400),('1.5',400),('',400),('abc',400)])
def test_score_bounds(app, client, score, expected):
    login(client, 'head')
    assert submit(client, score).status_code == expected
    with app.app_context():
        assert db.session.query(Score).count() == (1 if expected == 302 else 0)
        assert db.session.query(Audit).filter_by(action='score.submit').count() == (1 if expected == 302 else 0)


def test_duplicate_and_permissions(app, client):
    login(client, 'head')
    assert submit(client, activity=2).status_code == 403
    assert submit(client).status_code == 302
    assert submit(client, 70).status_code == 409
    assert post(client, '/scores/1/edit', {'score': '80', 'version':'1','reason':'No'}).status_code == 403
    post(client, '/logout')
    login(client, 'unassigned')
    assert submit(client, team=2).status_code == 403
    assert client.get('/register').status_code == 404
    assert client.get('/admin/users').status_code == 403
    with app.app_context():
        assert db.session.scalar(select(Score.score)) == 50


def test_corrections_stale_and_audit(app, client):
    login(client)
    assert submit(client).status_code == 302
    assert post(client, '/scores/1/edit', {'score':'0','version':'1','reason':'Corrected worksheet'}).status_code == 302
    assert post(client, '/scores/1/edit', {'score':'99','version':'1','reason':'Stale edit'}).status_code == 409
    assert post(client, '/scores/1/edit', {'score':'99','version':'2'}).status_code == 400
    with app.app_context():
        assert db.session.get(Score, 1).score == 0
        record = db.session.scalar(select(Audit).where(Audit.action=='score.correct'))
        assert record.before['score'] == 50 and record.after['score'] == 0
        assert record.reason == 'Corrected worksheet'
        with pytest.raises(IntegrityError):
            db.session.execute(text("UPDATE audit SET reason='tampered'"))
        db.session.rollback()


def test_standings_reports_ties_and_missing(app, client):
    login(client)
    for team, activity, score in [(1,1,75),(1,2,25),(2,1,100),(3,1,0)]:
        assert submit(client, score, team, activity).status_code == 302
    standings = client.get('/api/leaderboard').json
    assert [(r['name'],r['total_score'],r['rank'],r['activities_completed']) for r in standings] == [('Alpha',100,1,2),('Beta',100,1,1),('Gamma',0,3,1)]
    report = client.get('/reports')
    assert report.status_code == 200 and '—' in report.text
    assert 'Gamma,0,,0,1' in client.get('/reports?format=csv').text
    assert 'Alpha,75,25,100,2' in client.get('/reports?format=csv').text


def test_close_reopen_reset_keeps_history(app, client):
    login(client)
    submit(client)
    assert post(client, '/admin/scoring', {'scoring_open':'0','revision':'1','reason':'Finish'}).status_code == 409
    with app.app_context(): revision = db.session.get(EventState,1).revision
    assert post(client, '/admin/scoring', {'scoring_open':'0','revision':str(revision),'reason':'Finish'}).status_code == 302
    assert submit(client, team=2).status_code == 409
    assert post(client, '/scores/1/edit', {'score':'80','version':'1','reason':'Fix'}).status_code == 409
    assert post(client, '/admin/reset-scores', {'reason':'New rehearsal','confirmation':'wrong'}).status_code == 400
    assert post(client, '/admin/reset-scores', {'reason':'New rehearsal','confirmation':'RESET ALL SCORES'}).status_code == 302
    with app.app_context():
        assert db.session.query(Score).count() == 0
        assert db.session.query(Audit).filter_by(action='score.reset').count() == 1
        revision = db.session.get(EventState,1).revision
        assert not db.session.get(EventState,1).scoring_open
    assert post(client, '/admin/scoring', {'scoring_open':'1','revision':str(revision),'reason':'Start new rehearsal'}).status_code == 302
    assert submit(client).status_code == 302
    with app.app_context(): assert db.session.scalar(select(Score.id)) > 1


@pytest.mark.parametrize('path', ['/teams/1/delete','/activities/1/delete','/scores/1/delete','/admin/users/2/delete','/logout'])
def test_no_mutating_get(client,path):
    login(client)
    assert client.get(path).status_code == 405
    assert client.post(path).status_code == 400


def test_csrf_reset(client):
    login(client)
    assert client.post('/admin/reset-scores',data={'confirmation':'RESET ALL SCORES','reason':'forged'}).status_code == 400


def test_referenced_deletions_and_maximum(client):
    login(client,'head'); submit(client); post(client,'/logout'); login(client)
    for path in ['/teams/1/delete','/activities/1/delete','/admin/users/2/delete']:
        assert post(client,path,{'reason':'Delete'}).status_code == 409
    assert post(client,'/activities/1/edit',{'name':'Run','max_score':'49','reason':'Lower cap'}).status_code == 409


def test_query_count_constant(app,client):
    with app.app_context():
        statements=[]
        def counter(*args): statements.append(args[2])
        event.listen(db.engine,'before_cursor_execute',counter)
        client.get('/api/leaderboard'); initial=len(statements)
        db.session.add_all(Team(name=f'Team {i}') for i in range(30)); db.session.commit(); db.session.remove()
        statements.clear(); client.get('/api/leaderboard')
        assert len(statements)==initial==2
        event.remove(db.engine,'before_cursor_execute',counter)


def test_concurrent_duplicate_and_correction(app):
    clients = [app.test_client(),app.test_client()]
    for client in clients: login(client)
    tokens=[csrf(c,'/scores') for c in clients]
    def insert(i):
        return clients[i].post('/scores',data={'csrf_token':tokens[i],'team_id':'1','activity_id':'1','score':'30'}).status_code
    with ThreadPoolExecutor(2) as pool: assert sorted(pool.map(insert,range(2))) == [302,409]
    def correct(i):
        return clients[i].post('/scores/1/edit',data={'csrf_token':tokens[i],'version':'1','score':str(40+i),'reason':'Verified worksheet'}).status_code
    with ThreadPoolExecutor(2) as pool: assert sorted(pool.map(correct,range(2))) == [302,409]
    with app.app_context():
        assert db.session.query(Score).count()==1
        assert db.session.query(Audit).filter_by(action='score.correct').count()==1


def test_import_images_backup_restore(app,client,tmp_path):
    login(client)
    def import_csv(contents):
        return post(client,'/teams',{'csv_file':(io.BytesIO(contents),'teams.csv')},token_path='/teams')
    assert import_csv(b'Team Name\nDelta\nDelta\nAlpha\n').status_code==302
    assert import_csv(b'Team Name\nEpsilon\nInvalid,extra\n').status_code==400
    with app.app_context():
        assert db.session.query(Team).count()==4
    image=io.BytesIO(); Image.new('RGB',(1200,800),'red').save(image,'PNG'); image.seek(0)
    assert post(client,'/teams',{'name':'Image Team','image':(image,'image.png')},token_path='/teams').status_code==302
    assert post(client,'/teams',{'name':'Bad','image':(io.BytesIO(b'not an image'),'fake.png')},token_path='/teams').status_code==400
    assert submit(client,0).status_code==302
    response=post(client,'/admin/backup')
    assert response.status_code==200
    backup=tmp_path/'backup.zip'; backup.write_bytes(response.data)
    destination=tmp_path/'restored'
    result=restore(backup,destination)
    assert result['counts']['score']==1 and result['counts']['team']==5
    with sqlite3.connect(destination/'scoresheet.db') as restored_db:
        assert restored_db.execute('PRAGMA journal_mode').fetchone()[0]=='delete'
    restored_image=list((destination/'uploads').iterdir())[0]
    with Image.open(restored_image) as picture: assert max(picture.size)<=512
    with pytest.raises(ValueError): restore(backup,destination)
    recovery=create_app({'TESTING':True,'SECRET_KEY':'different-recovery-secret-'*3,'SQLALCHEMY_DATABASE_URI':f'sqlite:///{destination / "scoresheet.db"}','UPLOAD_FOLDER':str(destination/'uploads'),'HTTPS_ONLY':False})
    recovery_client=recovery.test_client()
    assert recovery_client.get('/api/leaderboard').json==client.get('/api/leaderboard').json
    login(recovery_client)
    assert submit(recovery_client,60,team=2).status_code==302
    assert recovery_client.get('/healthz').status_code==200


def test_backup_tampering_rejected(app,client,tmp_path):
    login(client)
    original=post(client,'/admin/backup').data
    target=tmp_path/'tampered.zip'
    with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(target,'w') as dest:
        for name in source.namelist():
            dest.writestr(name, b'bad' if name=='scoresheet.db' else source.read(name))
    with pytest.raises(ValueError,match='Checksum'): restore(target,tmp_path/'restored')


def test_login_redirect_and_throttle(app,client):
    token=csrf(client)
    response=client.post('/login?next=//evil.example',data={'csrf_token':token,'username':'head','password':'fixture-password-123'})
    assert response.location=='/dashboard'
    post(client,'/logout')
    for _ in range(10):
        assert client.post('/login',data={'csrf_token':csrf(client),'username':'head','password':'wrong'}).status_code==401
    assert client.post('/login',data={'csrf_token':csrf(client),'username':'head','password':'wrong'}).status_code==429


def test_admin_recovery_revokes_sessions_and_preserves_password(app,client):
    login(client)
    runner=app.test_cli_runner()
    result=runner.invoke(args=['admin-create','--username','admin','--email','admin@example.com','--password','different-password-123'])
    assert result.exit_code==0 and 'unchanged' in result.output
    result=runner.invoke(args=['admin-recover','--username','admin','--reason','Operator recovery','--password','replacement-password-123'])
    assert result.exit_code==0, result.output
    assert client.get('/admin/dashboard').status_code==302
    with app.app_context(): assert db.session.query(Audit).filter_by(action='admin.recover').count()==1


def test_native_wsgi_health_and_migration_safety(tmp_path):
    app=create_app({'TESTING':True,'SECRET_KEY':'test-secret-'*8,'SQLALCHEMY_DATABASE_URI':f'sqlite:///{tmp_path / "fresh.db"}','UPLOAD_FOLDER':str(tmp_path/'up'),'HTTPS_ONLY':False})
    assert app.test_client().get('/healthz').status_code==503
    runner=app.test_cli_runner()
    assert runner.invoke(args=['migrate']).exit_code==0
    assert runner.invoke(args=['migrate']).exit_code==0
    assert app.test_client().get('/healthz').status_code==200
    with sqlite3.connect(tmp_path/'legacy.db') as conn: conn.execute('CREATE TABLE team(id integer primary key)')
    legacy=create_app({'TESTING':True,'SECRET_KEY':'test-secret-'*8,'SQLALCHEMY_DATABASE_URI':f'sqlite:///{tmp_path / "legacy.db"}','UPLOAD_FOLDER':str(tmp_path/'up'),'HTTPS_ONLY':False})
    assert legacy.test_cli_runner().invoke(args=['migrate']).exit_code==1
    with sqlite3.connect(tmp_path/'legacy.db') as conn: assert conn.execute('SELECT COUNT(*) FROM team').fetchone()[0]==0


def test_database_constraints(app):
    with app.app_context():
        db.session.add(Score(team_id=1,activity_id=1,score=101,created_by=1))
        with pytest.raises(IntegrityError): db.session.commit()
        db.session.rollback()
        db.session.add(Score(team_id=999,activity_id=1,score=50,created_by=1))
        with pytest.raises(IntegrityError): db.session.commit()
        db.session.rollback()


def test_production_headers_and_https(app,client):
    app.config['HTTPS_ONLY']=True
    assert client.get('/login').status_code==400
    response=client.get('/login',base_url='https://localhost')
    assert response.status_code==200
    assert response.headers['Content-Security-Policy'].startswith("default-src 'self'")
    assert 'max-age' in response.headers['Strict-Transport-Security']
    assert 'no-store' in response.headers['Cache-Control']


def test_csv_headers_and_names_are_spreadsheet_safe(app,client):
    login(client)
    with app.app_context():
        db.session.get(Team,1).name='=SUM(1,2)'
        db.session.get(Activity,1).name='@malicious'
        db.session.commit()
    response=client.get('/reports?format=csv')
    assert "'@malicious" in response.text and "'=SUM(1,2)" in response.text


def test_long_report_splits_activity_columns(app,client):
    login(client)
    with app.app_context():
        db.session.add_all(Activity(name=f'Extra activity {i}',max_score=100) for i in range(18))
        db.session.commit()
    report=client.get('/reports').text
    assert report.count('report-page')==3
