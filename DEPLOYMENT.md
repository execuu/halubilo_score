# Deployment: PythonAnywhere free pilot

The chosen online candidate is PythonAnywhere Free, with Docker on the event laptop as a manual recovery option. **Local tests do not establish online readiness.** Public HTTPS verification, the actual-host workload test, and a venue-device rehearsal must pass before event use.

## Why this candidate, and its limits

PythonAnywhere supports this small native Flask application with a persistent filesystem, avoiding a database-platform rewrite. The free plan has one web worker, 512 MiB storage, and monthly expiry. New free accounts no longer include MySQL. PythonAnywhere explicitly discourages SQLite for production because its networked filesystem is slower, and SQLite WAL is not supported there. The pilot must use rollback journaling and prove the required event workload.

References checked during preparation:

- [Free account limits](https://help.pythonanywhere.com/pages/FreeAccountsFeatures/)
- [Available databases and SQLite guidance](https://help.pythonanywhere.com/pages/KindsOfDatabases/)
- [WAL restriction](https://www.pythonanywhere.com/forums/topic/36213/)
- [Docker is not supported](https://www.pythonanywhere.com/forums/topic/4019/)

Render Free is not suitable for this release's local SQLite database and uploads: its filesystem is ephemeral, free services sleep, and a free persistent disk is unavailable. See [Render's documented limitations](https://render.com/docs/free).

If the PythonAnywhere pilot fails the workload or reliability checks, do not label it event-ready. Keep the tested LAN deployment and revisit the hosting budget/provider. Do not hide free-tier limits with artificial keep-alive traffic.

## Prepare and upload a release

On the development computer:

```bash
make test
make assets
make release
```

Upload `output/releases/halubilo-1.0.0.zip` to the hosting account. Extract into `~/halubilo_scoresheet`. The archive has a manifest and contains compiled CSS; Node and Docker are not required on PythonAnywhere. It intentionally excludes `.env`, databases, account credentials, and uploaded images.

In a PythonAnywhere Bash console:

```bash
cd ~/halubilo_scoresheet
python3.13 -m venv .venv
. .venv/bin/activate
pip install --no-cache-dir -r requirements.txt
python deploy_pythonanywhere.py --prepare
flask --app app:create_app admin-create
```

The helper creates a private production `.env` only if absent, initializes a fresh versioned database, and prints WSGI setup instructions. It never creates a default password or replaces an existing database. Set `EVENT_NAME` in `.env` before the event. Keep the release source outside publicly mapped directories.

## Configure the web app

Create a manually configured Python 3.13 web app in the Web tab. Use the matching virtualenv and source directory. The WSGI editor should contain the following, with YOUR_USERNAME replaced by the real account:

```python
import sys
sys.path.insert(0, '/home/YOUR_USERNAME/halubilo_scoresheet')
from wsgi import application
```

Set the virtualenv to `/home/YOUR_USERNAME/halubilo_scoresheet/.venv`.
Map `/static/` to `/home/YOUR_USERNAME/halubilo_scoresheet/static`. Team images are served through `/uploads/` by Flask; do not map the whole `instance/` directory. In particular, the database must never be downloadable as a static file.

Required production settings (the helper writes them):

```dotenv
APP_ENV=production
HTTPS_ONLY=1
SQLITE_WAL=0
# SECRET_KEY is a generated private value, never the placeholder from older docs.
# DATABASE_URL and UPLOAD_FOLDER must use persistent absolute paths.
```

Reload the web app and visit its HTTPS hostname. PythonAnywhere runs WSGI itself; do not launch Gunicorn or Flask's development server in a console. No ProxyFix or trust of arbitrary X-Forwarded headers is enabled.

## Online acceptance gates

- `/healthz` returns HTTP 200 over HTTPS, and the homepage and login load.
- Admin creation, assigned-head login, zero/max scores, duplicate rejection, correction, audit history and closing/reopening work on the real host.
- The actual event phones can load pages and submit over the venue network.
- Records and images survive a Web-tab reload.
- All page assets load locally, without CDN requests or console errors.
- A downloaded backup restores in the event laptop's Docker runtime; totals match and a new score can be submitted there.
- At 30 teams, 20 activities, 10 concurrent heads and 50 viewers, run a 15-minute rehearsal with no lost/duplicate scores, incorrect totals or unexpected server errors. Required online p95 for submissions and leaderboard requests is below two seconds. Pass `--p95-ms 2000` to use the online gate; the script defaults to the stricter one-second local gate.

For capacity testing, use a separate empty rehearsal database and upload directory. Set `REHEARSAL_ONLY=1` and a temporary `REHEARSAL_PASSWORD`, run `python scripts/seed_rehearsal.py`, and point the web app at that database. Run `scripts/load_test.py` from the local computer with its `--url` set to the HTTPS hostname and its credentials in a private env file. It refuses an unexpected/nonempty fixture. Restore the fresh event configuration afterward, reload, create real operator accounts, and remove rehearsal credentials from production configuration.

## Updates, monitoring, and rollback

Before any update, close scoring and download a backup. Preserve the previous release and database paths. Upload the new release, install its pinned dependencies, run the documented migrations, reload and verify health plus a read-only results comparison. If verification fails, restore the prior source and configuration; use a fresh restore directory if the schema changed. Do not delete or overwrite the only database copy.

Check health, free storage, error logs and account expiry before each event. Renew the free web app monthly. During the event, follow the five-minute download schedule and retain worksheets. Free hosting has no event availability guarantee; use the [manual recovery procedure](docs/RECOVERY.md) when needed.
