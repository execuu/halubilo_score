# Troubleshooting

| Symptom | Action |
| --- | --- |
| Container unhealthy / HTTP 503 | Run `make logs`. On a fresh install run `make migrate`, then `make start`. Never delete the database to fix an error. |
| Secret/configuration startup error | Run `make setup` if `.env` is absent. Existing `.env` is preserved. Set a unique secret of at least 32 characters; do not reuse the example placeholder. |
| Cannot log in | Verify the username; after 10 failures for one account, wait 15 minutes or use `make recover`. Recovery revokes old sessions and records its reason. |
| 400 CSRF error | Reload the form and log in again if needed. Do not disable CSRF protection. |
| Duplicate score / HTTP 409 | Review Scores. A final score already exists; an admin must correct it rather than resubmit. |
| Stale score or event revision | Reload and review changes made since the page opened. Retrying the stale form is intentionally rejected. |
| Score rejected | Use a whole number from zero through that activity's maximum. Confirm the activity assignment and that scoring is open. |
| Database busy / HTTP 503 | Check logs and whether another process is running a long write. Do not retry blindly; first check if the score exists. Repeated lock errors mean the workload/host must be re-evaluated. |
| LAN cannot connect | Confirm `make status` succeeds on loopback and the printed LAN address. Check same router, firewall, guest-network isolation and correct port. Docker bridge addresses are not client URLs. |
| Login loops in LAN mode | `.env` must use `APP_ENV=lan` and `HTTPS_ONLY=0`; secure cookies require HTTPS. Restart after configuration changes. |
| Production rejects HTTP | Use the HTTPS URL. The hosting WSGI server must report the actual HTTPS scheme. Do not trust arbitrary forwarded headers. |
| Missing team image | Restore from the consistent backup or upload a replacement. Backups deliberately fail if a referenced image is missing. |
| PythonAnywhere expiry or storage limit | Renew the free web app monthly; check remaining disk space and retain backup archives on the event laptop. |
| Unversioned legacy database refused | Preserve the file. This fresh-event release will not silently convert or delete inherited records. |

After an outage, use the recovery runbook. Reconcile from retained activity worksheets and audit history; never sum conflicting snapshots or run two authoritative scoring systems.
