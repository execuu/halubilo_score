#!/usr/bin/env python3
"""Run inside your PythonAnywhere virtualenv to prepare/check the source release."""
import argparse
import getpass
import os
from pathlib import Path
import secrets
import sys

root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--prepare',action='store_true',help='Create production configuration if absent and initialize a fresh DB.')
args=parser.parse_args()
if sys.version_info[:2] != (3,13):
    raise SystemExit('Use the Python 3.13 virtualenv for this release.')
if args.prepare:
    target=root/'.env'
    if not target.exists():
        with target.open('x') as output:
            os.chmod(target,0o600)
            output.write(f'SECRET_KEY={secrets.token_hex(32)}\nAPP_ENV=production\nHTTPS_ONLY=1\nSQLITE_WAL=0\nEVENT_NAME=Halubilo\nDATABASE_URL=sqlite:///{root / "instance/scoresheet.db"}\nUPLOAD_FOLDER={root / "instance/uploads"}\n')
        print('Created private production configuration.')
from app import create_app
app=create_app()
if not app.config['HTTPS_ONLY'] or not app.config['SESSION_COOKIE_SECURE'] or app.config['SQLITE_WAL']:
    raise SystemExit('Production check failed: require APP_ENV=production, HTTPS_ONLY=1 and SQLITE_WAL=0.')
if args.prepare:
    result=app.test_cli_runner().invoke(args=['migrate'])
    print(result.output.strip())
    if result.exit_code: raise SystemExit(result.exit_code)
with app.test_client() as client:
    response=client.get('/healthz',base_url='https://localhost')
    if response.status_code!=200: raise SystemExit('Readiness failed. Run --prepare or review the database configuration.')
print('Local production checks passed. This does not verify the public website or hosting capacity.')
print('In the PythonAnywhere WSGI editor use:')
print(f'import sys\nsys.path.insert(0, {str(root)!r})\nfrom wsgi import application')
print(f'Set the virtualenv to your Python 3.13 environment; map /static/ to {root / "static"}.')
print('Create the operator account with: flask --app app:create_app admin-create')
print('Reload the web app, then verify the public HTTPS URL and run the event rehearsal.')
