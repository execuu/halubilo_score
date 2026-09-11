# Hosted event operations

Public URL: https://halubilo-scoresheet.onrender.com

The event runs on Render Free in Singapore. Scores and accounts live in the dedicated Supabase project `halubilo-scoresheet` (`cmvpdamcnnzodvpumxsv`), also in Singapore. Team images live in its private `team-images` bucket. The PostgreSQL tables use the private `halubilo` schema. Database SSL enforcement is enabled.

Render service: `srv-dahne6jm8hqs73cit9j0`. Source branch: `deploy/render-supabase`. Automatic deployment is disabled. The deployment configuration is in `render.yaml`; the live service was provisioned directly through the Render API using the same settings. It is not attached to automatic Blueprint synchronization.

## Verified deployment

Deployed 11 September 2026, release **1.1.1**, application commit `f8f06286643be73842b9f41014a82a91a1403a38`, Render deployment `dep-dahocibm8hqs73cmu480`. Public HTTPS admin login, the fresh event state, reports, audit and a downloaded initial backup passed. A mobile Chromium browser displayed the real administrator dashboard with zero teams/activities/scores and one user.

The isolated 15-minute hosted rehearsal accepted 600 scores and served 4,500 leaderboard reads with zero request errors and matching totals/ranks. Scoring p95 was 1.49 seconds; leaderboard p95 was 0.83 seconds. The cloud-to-Docker recovery drill preserved records, audit history and images, then accepted a new score on the recovery copy. Full evidence and limitations are in [VERIFICATION.md](VERIFICATION.md).

The disposable cloud rehearsal project was removed after verification. Its downloaded backup and stopped local recovery volume are retained separately. Your real event starts clean.

## Administrator and event setup

Open the private local file `instance/cloud-admin-credentials.txt` for the administrator login. The event starts with one administrator and no teams, activities or scores. Create activity-head accounts through Admin → Users. Follow README.md for team imports, scoring, corrections, closing and reports.

Initial administrator credentials are not retained in Render's runtime environment. `.env.cloud` is a private local deployment/recovery configuration and is excluded from Git. Do not put its contents into issues or chat.

To recover the cloud administrator from this trusted laptop, run the following command in an interactive terminal and enter the username, reason and new password when prompted:

```bash
.venv/bin/dotenv -f .env.cloud run --override -- .venv/bin/flask --app app:create_app admin-recover
```

This targets the cloud database, records the recovery and revokes that account's existing browser sessions. Update the private credential file after changing the password.

## Backups and recovery

Download a backup from Admin every five minutes during scoring and after each completed activity. Keep it on the event laptop and a second trusted device. Backups contain private account hashes, scores, history and images. Supabase Free does not provide automatic database backups.

Use docs/RECOVERY.md to restore a downloaded backup into a NEW LAN volume. Cloud backups use the same SQLite recovery format. Close the cloud source first if reachable, coordinate a single authoritative scoring system, and record any worksheet scores entered since the backup. Cloud and LAN do not synchronize automatically.

The initial fresh-event backup is stored privately at `backups/cloud-initial-event.zip` after final verification. A successful local restore does not establish venue-router connectivity: run `make status` and test actual phones on the event Wi-Fi before event day.

## Later deployments

Push reviewed changes to the deployment branch, wait for GitHub Actions to pass, download a backup, then manually deploy that commit in Render. Deploy outside live scoring. Keep `SECRET_KEY`, the database URL and the Supabase project/bucket stable.

For a process restart with the same deployed code/configuration:

```bash
~/.local/bin/render restart srv-dahne6jm8hqs73cit9j0 --confirm
```

After changing code or environment variables, use a deployment instead of a restart. Verify `/healthz`, admin login, persistence and image display afterwards. A restart uses the current deployed environment and does not apply pending environment changes.

Free Render instances can sleep after inactivity, and provider quotas still apply. Open and check the site before participants arrive. Keep the LAN fallback available. Do not use artificial keep-alive traffic to evade free-plan limits.

Provider dashboards:

- https://dashboard.render.com/web/srv-dahne6jm8hqs73cit9j0
- https://supabase.com/dashboard/project/cmvpdamcnnzodvpumxsv
