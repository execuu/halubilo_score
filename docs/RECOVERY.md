# Event backup and recovery runbook

## Before the event

- Keep this tested release and its Docker image on the event laptop. Start it once before event day so internet is not required to download images or dependencies.
- Bring a router that permits communication between devices and keep the laptop on power. Record the LAN URL from `make status` and test it on an actual scorekeeper's phone.
- Keep the local `.env` private. It should have its own secret and `APP_ENV=lan`, `HTTPS_ONLY=0`.
- Download the latest online backup to `backups/` every five minutes during scoring and after each activity. Verify the download completed. Keep backup copies on a separate device as well.
- Heads retain the original activity worksheets. Anything accepted after the latest downloaded backup might need to be re-entered after a failure.

## Switching from online to LAN

1. Announce a pause and get confirmation from every scorekeeper. Nobody should continue entering scores on mobile data or another online connection. If the online app is reachable, close scoring and download a final backup.
2. Choose the most recent completed backup. Keep the online snapshot and local snapshot as separate files. Do not modify or delete the online database.
3. Restore into a **new** Docker volume. Replace the backup filename below with the selected file. Use a new volume name for each recovery attempt.

```bash
docker volume create halubilo_recovery_event
# The pipe passes the private ZIP without exposing host-directory permissions.
docker run --rm -i --network none \
  -v halubilo_recovery_event:/data \
  halubilo-scoresheet:local \
  python scripts/restore.py - /data < backups/SELECTED-BACKUP.zip
```

The restore refuses to overwrite an existing database. It verifies archive paths, checksums, schema, referential integrity, score bounds/uniqueness, and team image references, then normalizes the restored copy to rollback journaling for portability. The output gives restored record counts and the backup's UTC timestamp.

4. Start recovery on port 8083 so the original local setup stays intact. The backup contains accounts but not the cloud session secret, so users log in again.

```bash
docker run -d --name halubilo-recovery \
  --restart unless-stopped --init --read-only \
  --tmpfs /tmp:size=64m,mode=1777 --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --env-file .env \
  -e APP_ENV=lan -e HTTPS_ONLY=0 -e SQLITE_WAL=0 \
  -e DATABASE_URL=sqlite:////data/scoresheet.db \
  -e UPLOAD_FOLDER=/data/uploads \
  -p 8083:8080 -v halubilo_recovery_event:/data \
  halubilo-scoresheet:local
curl --fail http://localhost:8083/healthz
```

5. Log in at `http://LAPTOP-LAN-IP:8083`. Compare the restored counts, report totals and last audit entries with the selected backup. If the snapshot was closed, the admin reopens scoring with a recovery reason.
6. Re-enter missing submissions from retained worksheets; duplicate protection prevents a second score for the same pair. Resolve different values through an admin correction with a reason, not by summing them.
7. Confirm that every scorekeeper uses the LAN address. Continue with the local recovery copy as the single authority for the rest of the event. Target recovery time is under 15 minutes; actual timing must be rehearsed.

If the laptop cannot be recovered promptly, record on worksheets until a verified system is available. Do not invent missing scores or mark missing submissions as zero.

## After connectivity returns

Keep online scoring out of use. Close it when reachable. Download and preserve both databases before reconciliation. Compare score pairs and audit histories for submissions newer than the last common backup. An administrator resolves differences with reasons in the authoritative local system. Export final reports and a final backup. The automatic restore command targets LAN SQLite. Continue the event on that recovered LAN copy. Returning its newer data to Supabase requires a separately reviewed migration and total checks; do not resume the stale cloud database.

## Back up the recovery container

```bash
docker exec halubilo-recovery flask --app app:create_app backup /tmp/recovered-event.zip
docker cp halubilo-recovery:/tmp/recovered-event.zip backups/recovered-event.zip
chmod 600 backups/recovered-event.zip
```

The admin backup button works in the recovery container too. Do not rely on a file left inside `/tmp`: it is temporary.

## Native restore (including PythonAnywhere)

Stop/disable the target web app first. Restore into a new private directory and point `DATABASE_URL` and `UPLOAD_FOLDER` at it; keep the previous directory intact.

```bash
python scripts/restore.py downloaded-backup.zip instance/restored-event
```

On PythonAnywhere, use the existing production secret or generate a new one, `APP_ENV=production`, `HTTPS_ONLY=1`, and `SQLITE_WAL=0`. Reload after updating paths. Run the readiness check and compare reports before reopening scoring.
