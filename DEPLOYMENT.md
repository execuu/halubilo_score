# Deployment: Render Free + Supabase Free

The cloud target is Render for Flask/Gunicorn, Supabase PostgreSQL for scores and accounts, and a private Supabase Storage bucket for team images. Docker with SQLite remains the manual LAN recovery option. **The cloud integration is prepared; actual account deployment and hosted verification are still pending.**

## Account setup

Use a fresh Supabase project dedicated to this event. Choose Singapore where available to match the Render Blueprint. Do not reuse a project holding unrelated data without reviewing ownership and limits.

1. In Supabase, obtain the PostgreSQL **Session pooler** connection string (port 5432) from **Connect**. Use `postgresql+psycopg://.../postgres?sslmode=require`, with the database password URL-encoded. The session pooler supports IPv4. Do not use transaction pooling for this configuration.
2. Create a **private** Storage bucket named `team-images`, with a 2 MiB file limit and `image/jpeg` allowed. Keep it private and add no anonymous write policies. The server uploads normalized JPEGs and proxies only images referenced by teams.
3. Obtain the project HTTPS URL and legacy server-only `service_role` key. Never use the anon/publishable key for the server storage credential, or expose the service role key to the browser.
4. In Render, create a Blueprint from this GitHub repository and the branch containing `render.yaml`. Review that the web service plan is **Free** and no paid database or disk is being created.
5. Fill the secret fields below. Render generates `SECRET_KEY`. The first startup creates the private database schema and administrator, then starts Gunicorn. Later starts preserve scores and passwords. Automatic deployments are disabled to avoid changing the app during an event.

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Supabase session pooler URI with `sslmode=require` |
| `SUPABASE_URL` | Project URL, e.g. `https://PROJECT.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only legacy service role key |
| `SUPABASE_STORAGE_BUCKET` | `team-images` |
| `INITIAL_ADMIN_USERNAME` | Chosen initial administrator name |
| `INITIAL_ADMIN_EMAIL` | Administrator email |
| `INITIAL_ADMIN_PASSWORD` | Unique password of at least 12 characters |
| `EVENT_NAME` | Event display name |

After verifying the first login, remove `INITIAL_ADMIN_PASSWORD` from Render's environment. It is not needed for restarts or later deployments once an administrator exists. Keep `SECRET_KEY` stable across deploys; rotating it logs out users. Use the existing audited CLI recovery command via a trusted local environment connected to the cloud database if recovery is needed.

The app creates its tables in the `halubilo` schema, outside Supabase's exposed `public` schema. Do not add `halubilo` to the Data API's exposed schemas. The Flask backend owns authorization. PostgreSQL constraints and triggers enforce duplicate protection, bounds, and immutable audit history; a transaction-scoped event lock orders all application writes and backup snapshots.

## Let the coding agent deploy

The repository and GitHub authentication are available locally. Render and Supabase account access must also be made available. A private local file (mode 0600, outside Git or named `.env.cloud`) can hold `RENDER_API_KEY` and `SUPABASE_ACCESS_TOKEN` for account management. Tell the agent only the file path and chosen project/workspace, not the secret values in chat. For an existing Supabase project, deployment also needs its database password/connection URI and server storage credential. Account tokens alone do not reveal an existing database password.

No account tokens belong in `render.yaml`, Git, screenshots, logs, or backup archives. `RENDER_API_KEY` and `SUPABASE_ACCESS_TOKEN` are deployment credentials and are not application environment variables.

## Verification before event use

1. Verify the public HTTPS login, secure cookies, administrator access and health endpoint.
2. In an isolated rehearsal project, repeat the 30-team / 20-activity workload with 10 scorekeepers and 50 viewers. The cloud target is p95 below two seconds, no lost or duplicate scores, and independently matching totals/ranks. Local PostgreSQL tests cannot prove free-host capacity.
3. Upload a team image, submit zero and maximum scores, test forbidden non-admin corrections and an audited admin correction. Recreate the service and confirm records/images persist.
4. Close scoring, download a backup from Admin, restore into a new LAN volume using [RECOVERY.md](docs/RECOVERY.md), compare standings/images/audit, reopen only the recovery copy with a reason, then submit a new score. Coordinate exactly one authoritative scoring site.
5. Test from actual event phones and the venue router. Restore the public event to a fresh approved state before real scoring.

Cloud backups contain the same portable SQLite snapshot and referenced images as LAN backups. Supabase credentials are not included. The source backend does not need to be available to restore a downloaded archive. Retain downloaded backups outside both providers; a free Supabase project does not include automatic database backups.

An upload can leave an unreferenced object if its database transaction fails. Such an object is not served or included in backups. Images use immutable random names; do not delete bucket contents while the app is live or while making a backup.

## Free-tier limitations

Render Free can sleep after inactivity, restart, and has no persistent local disk. The app refuses Render startup with SQLite or local image storage. Supabase Free provides 500 MB database storage and 1 GB file storage, pauses inactive projects, and has no automatic database backups. Quotas and account availability must be checked in the actual dashboards. Never use artificial keep-alive traffic to conceal these limits.

References checked during implementation:

- [Render free services](https://render.com/docs/free)
- [Render Blueprint configuration](https://render.com/docs/blueprint-spec)
- [Supabase connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supabase Storage access control](https://supabase.com/docs/guides/storage/security/access-control)
- [Supabase free plan](https://supabase.com/pricing)

The earlier native SQLite hosting option is preserved in [PYTHONANYWHERE.md](docs/PYTHONANYWHERE.md).
