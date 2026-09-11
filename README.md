# Halubilo event scoresheet

A single-event Flask application for an administrator and activity heads. Each team receives one whole-number score per activity. Standings sum raw points; equal totals share competition ranks (1, 2, 2, 4). A recorded zero is different from an unsubmitted score. This release starts a fresh event and refuses to modify an inherited, unversioned database.

The deployed event is at **https://halubilo-scoresheet.onrender.com**. See the [hosted operator handoff](docs/HOSTED_DEPLOYMENT.md) for administrator access, backups and deployment details.

For online hosting, see [Render + Supabase deployment](DEPLOYMENT.md). The cloud backend uses PostgreSQL and private object storage; LAN installations continue using SQLite and local images. Both produce portable LAN recovery archives.

## Start on this computer

Requirements: Docker Engine with Compose, Python 3 for setup, and an event router for LAN access. Docker builds the Python 3.13/Gunicorn runtime and local CSS; host Python packages are not needed.

```bash
make init       # create private configuration, build, initialize a fresh database
make start      # start and wait for readiness
make admin      # choose username, email and a strong password
make status     # health plus current localhost and LAN URLs
```

Visit `http://localhost:8080`. Other devices use the LAN URL printed by `make status`. Port 8080 is configurable with `PORT` in `.env`. Do not use a Docker 172.x address for event devices. The router must permit devices to reach each other; guest Wi-Fi/client isolation can prevent this.

The public home page shows standings. Use Log in for the operator interface. Passwords have a 12-character minimum; there is no shared/default administrator password. If this checkout was bootstrapped by the implementation session, its private initial login is in `instance/admin-credentials.txt` (not included in Git or releases).

```bash
make stop       # stop without deleting data
make restart    # recreate containers, preserve volumes, wait for readiness
make logs       # recent service logs
make backup     # save a consistent private backup to ./backups/
make recover    # recover an existing admin account, with a required audit reason
make test       # isolated container regression tests; no network or event data
```

**Do not run `docker compose down -v`: it deletes the event volumes.** Building, stopping and restarting do not clear scores. `make init` is repeatable against this release's versioned database and does not reset accounts.

## Operator workflow

1. Log in as admin. Add teams individually or import UTF-8 CSV with exactly one `Team Name` column. Duplicate names are skipped; malformed rows reject the entire import. Images are optional, decoded and reduced to 512 pixels (2 MiB upload limit).
2. Add activities and their maximum scores (1–1000). Each activity contributes its actual points directly: an activity capped at 100 has twice the possible contribution of one capped at 50. There are no weights, rounds, penalties, or automatic tiebreakers.
3. In Users, create one account per activity head, assigned to its activity. Users can be reassigned or disabled. Account changes invalidate that user's prior sessions. Only admins can administer accounts; public registration is disabled.
4. Heads select a team and enter one final score between 0 and the activity maximum, inclusive. They can view records for their assigned activity. Keep a separate activity worksheet until the event is over.
5. A duplicate submission is rejected with no change to totals. If the connection fails, check the existing recorded score before retrying. An acknowledged success means the score and its audit entry committed together.
6. To correct a score, an admin opens Scores → Correct, enters a reason and saves. Another admin's newer edit causes a conflict instead of being overwritten. A score entered for the wrong team/activity can be deleted with a reason and explicit confirmation, then submitted correctly. The old value remains in history.
7. Review Reports for missing cells (—) versus recorded zeros. The admin dashboard shows recorded versus expected submissions. All results remain provisional while scoring is open. Close scoring to stop submissions and corrections. Reopening requires a reason.
8. Print or save the report using the browser, and export CSV. Equal totals keep equal ranks; award tiebreak decisions are handled by organizers outside this release.

The public page and score-page standings update every 10 seconds while visible. A connection warning preserves the last received standings. Score-entry fields are not refreshed. Dates display in Asia/Manila; the database stores UTC.

## Backups and event recovery

Download **Admin → Download backup ZIP** to the event laptop every five minutes and after each completed activity. Confirm the file is present before considering the backup complete. Archives contain password hashes and private audit data; do not publish them. They contain the database and referenced images, not the application secret or server configuration.

Use the detailed [recovery runbook](docs/RECOVERY.md). Restore only into a NEW, offline directory/volume. The restore command verifies checksums, schema, foreign keys, score bounds, uniqueness and image references. It will not overwrite existing data. Never copy a live SQLite database file as a substitute for the backup command.

The global reset is deliberately separate from recovery. Close scoring, download a backup, and type `RESET ALL SCORES` with a reason. Current scores are removed; audit history remains; scoring stays closed. Referenced teams, activities and accounts cannot be deleted. Disable referenced accounts instead.

## Architecture and storage

- `app.py`: Flask factory, models, transactions, role checks, score aggregation, reports and operator CLI.
- `migrations/001_initial.sql`: versioned fresh-event schema, uniqueness/bounds and immutable audit triggers.
- `templates/` and `static/`: server-rendered pages and compiled local CSS; no CDN required at event time.
- `scripts/`: configuration, backup restoration, release packaging, rehearsal fixtures and load testing.
- `tests/`: regression cases covering correctness, permissions, concurrent requests, recovery and configuration.

SQLite admits one writer. Mutating HTTP requests acquire the write reservation before reading roles, score limits, event status or existing scores, so competing writes and backups are serialized. Score and audit changes commit together. Standings use one aggregate query, plus one event-status query, independent of team count. Score/audit histories paginate at 50 rows.

The container runs as UID 10001, with a read-only root filesystem and writable named volumes for `/data` and `/backups`. The database is `/data/scoresheet.db`; images are `/data/uploads`. Native execution defaults to `instance/scoresheet.db` and `instance/uploads`. Paths can be configured using `DATABASE_URL` and `UPLOAD_FOLDER`.

`/livez` checks the process; `/healthz` verifies the schema and event state. Gunicorn logs go to `make logs`. Local LAN mode uses HTTP; production mode requires HTTPS and secure cookies. This release supports SQLite for LAN use and PostgreSQL for cloud use. Enable WAL only on local disk, never on PythonAnywhere's network filesystem.

## Development and release

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
python3 scripts/setup.py
.venv/bin/flask --app app:create_app migrate
.venv/bin/flask --app app:create_app admin-create
.venv/bin/flask --app app:create_app run
npm ci && npm run build
.venv/bin/pytest -q
.venv/bin/pip-audit -r requirements.txt --progress-spinner off
make release
```

Runtime dependencies are pinned in `requirements.txt`; development dependencies are constrained to the same runtime pins. Update `.in` files deliberately and recompile the locks with pip-tools, then repeat tests and the dependency audit. CSS is checked in for native WSGI hosting and rebuilt in Docker. The release archive excludes event data, credentials, `.env`, and test fixtures.

See [DEPLOYMENT.md](DEPLOYMENT.md) for Render + Supabase deployment, [verification evidence](docs/VERIFICATION.md) for measured gates, and [troubleshooting](docs/TROUBLESHOOTING.md) for common failures. Local success does not certify the online host or venue network.
