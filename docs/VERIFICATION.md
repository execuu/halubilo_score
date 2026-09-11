# Verification evidence — 11 September 2026

## Phase status

| Phase | Status | Evidence |
| --- | --- | --- |
| Repository audit and operating model | Complete | SYSTEM_AUDIT.md; inherited runtime failure reproduced with an isolated database |
| Reproducible local/container runtime | Complete | Python 3.13.15, Gunicorn, health checks, persistent named volumes, private admin setup |
| Correctness and deployment hardening | Complete locally | 29 regression cases passed in the Python 3.13 test image with networking disabled |
| Performance and mobile/report verification | Complete locally | Fifteen-minute workload, Chromium 390x844 checks, rendered three-page A4 report |
| Backup/recovery implementation and automated drill | Complete locally | Verified restore, image equality, closed source, audited reopening and successful new submission |
| PythonAnywhere pilot / online approval | Pending account access and actual-host rehearsal | DEPLOYMENT.md lists the public HTTPS and capacity gates |
| Physical event-device/router rehearsal | Pending organizer/venue check | Host loopback and LAN interface are verified; an actual remote phone was not available |

## Automated regression coverage

29 passing cases cover zero/max/invalid scores, duplicate protection, concurrent duplicate submissions and stale corrections, role/assignment restrictions, CSRF, POST-only mutations, event closing/reopening, reset history retention, immutable audit rows, referenced-data protections, ties and missing scores, CSV atomicity and spreadsheet escaping, image decoding/resizing, backup tampering, restore portability, account recovery/session revocation, login throttling/redirects, schema safety, and production headers.

`make test` builds the isolated test target and runs it without network access. It never mounts the event database. The final runtime dependency audit reported no known vulnerabilities; npm audit also passed. These are point-in-time checks, not a guarantee against future advisories.

## Measured workload

Started at 2026-09-10T23:04:27.593112+00:00. Scheduled window: 900 seconds; measured request window: 899.82 seconds. Runtime: one Gunicorn worker with four threads, Python 3.13, SQLite on local storage. This is a local host test, not a PythonAnywhere benchmark.

| Request | Count | p95 | Maximum |
| --- | ---: | ---: | ---: |
| Score submission | 600 | 618.05 ms | 2865.69 ms |
| Leaderboard | 4500 | 56.06 ms | 2500.37 ms |
| Score-entry page | 600 | 367.9 ms | 1471.37 ms |

30 teams × 20 activities; 10 simultaneous scorekeeper threads; 50 viewers polling every ten seconds. **600 of 600 expected scores, zero request errors, matching totals and competition ranks.** Both required p95 measurements passed the one-second local gate. Higher maximum latencies are shown above rather than hidden by the percentile.

The inherited leaderboard took 22 queries for 21 teams. The current API uses two queries including event status, and the regression test confirms that query count stays constant as teams are added. Histories paginate at 50 rows.

Raw evidence: `output/load-test.json`. Repeat instructions: PERFORMANCE.md. The measured score-writing and leaderboard paths were unchanged by the subsequent report-layout and backup-resource cleanup work.

## Browser and printed output

Chromium verified login and zero-score submission at 390x844, admin correction from 0 to 75 with a reason, the mobile navigation, and report access. Score and notes inputs survived a ten-second leaderboard refresh; no page-level horizontal overflow was detected. External requests were blocked while the local scoring workflow ran. The final report page reported no external asset dependencies.

The report groups at most eight activity columns per table. The 30-team, 20-activity fixture generated three A4 landscape pages. Rendered pages were inspected for clipping, column wrapping and row completeness. Example evidence is under `output/playwright/` and `output/pdf/`; all records shown are rehearsal fixtures.

## Recovery and persistence

The real local event container survived recreation with its administrator intact, and `make backup` exported a private archive. The separate UI rehearsal backup contained 30 teams, 20 activities, 21 accounts, a scored/corrected record and a team image.

Restoration into a new Docker volume passed integrity, reference, bounds, uniqueness and checksum checks. Restored standings matched the backup exactly; image bytes were identical. The source remained closed and unchanged while the recovered copy was reopened with a reason and accepted a new score. Measured download-to-continuation time: **133.66 seconds**. This automated drill does not include organizing real participants or diagnosing a venue router.

Raw evidence: `output/recovery/recovery-result.json`. Restores normalize journaling to DELETE so a local WAL backup is portable to PythonAnywhere. Existing restore destinations are refused. The original source and rehearsal volumes are preserved.

## Handoff environment

Local event URL: `http://localhost:8080`; verified LAN interface URL: `http://192.168.0.103:8080`. The LAN address is time-specific; run `make status` after changing routers. Both `/healthz` requests returned 200. The container runs as UID 10001 with a read-only root filesystem and all capabilities dropped.

The fresh event contains an administrator and no rehearsal teams, activities or scores. Initial local credentials are in the private, ignored `instance/admin-credentials.txt`. Rehearsal and recovery data use separate Docker volumes.

The first build encountered a full root filesystem. Unused build cache was pruned, the build succeeded, and later disk checks showed approximately 20 GiB available. No organizer database or running unrelated application was removed.

## Remaining release gates

The source release manifest was verified and the PythonAnywhere preparation helper passed both fresh initialization and repeat initialization under Python 3.13 with networking disabled. The archive contains no event database or secrets. Evidence: `output/releases/native-check.json`. A PythonAnywhere username/account session has not been provided, so no public site has been provisioned or declared ready. The actual-host HTTPS, persistence, workload and venue-device tests remain required before event use. Free-host limits remain material; refer to DEPLOYMENT.md.
