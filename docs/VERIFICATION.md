# Verification evidence

## Release 1.1.1 backup verification

The PostgreSQL-to-SQLite exporter now preserves consumed score IDs even when all current scores have been reset. Its regression was reproduced before the fix and passes afterwards. Backups release the database writer lock before fetching immutable images; a concurrent regression verifies a new score commits while an image download is blocked, while the downloaded snapshot remains consistent.

Final local Python 3.13 container results: **36 PostgreSQL tests passed; 35 SQLite tests passed with one PostgreSQL-only case skipped.** Hosted load testing is tracked separately; no local timing is substituted for it.

## Cloud backend update

The Render + Supabase integration adds PostgreSQL, private image storage, automatic fresh-schema startup and portable PostgreSQL-to-SQLite recovery archives. The original 29 workflow cases pass against both local SQLite and PostgreSQL 17. The initial cloud integration passed 34 PostgreSQL cases and 33 SQLite cases (one PostgreSQL-only case skipped); release 1.1.1 adds the two backup regressions reported above. The dependency audit found no known vulnerabilities. Five additional cloud cases cover remote image persistence/recovery, failed uploads, HTTPS proxy handling, refusal of ephemeral Render storage and PostgreSQL schema boundaries. Storage HTTP responses are simulated in local tests. Actual Supabase private upload/read/delete, anonymous denial, private database schema boundaries and SSL enforcement were subsequently verified in the dedicated hosted projects.

The earlier load timings below describe release 1.0.0 on SQLite only. They do not establish PostgreSQL, Supabase Storage or Render capacity.

## Hosted capacity — 11 September 2026

Release 1.1.1 ran on Render Free in Singapore with one Gunicorn worker and four threads, using Supabase PostgreSQL and private Storage in Singapore. A GitHub-hosted runner exercised the actual public HTTPS service against an isolated rehearsal project. Scheduled window: 900 seconds; measured window: 900.07 seconds, starting 04:24:10 UTC.

| Request | Count | p95 | Maximum |
| --- | ---: | ---: | ---: |
| Score submission | 600 | 1492.34 ms | 2132.79 ms |
| Leaderboard | 4500 | 833.69 ms | 1742.05 ms |
| Score-entry page | 600 | 1244.01 ms | 1657.68 ms |

Thirty teams, twenty activities, ten scorekeeper threads and fifty viewers polling every ten seconds produced **600 accepted scores, zero request errors and independently matching totals and competition ranks**. Both required p95 measurements passed the two-second hosted gate. This measures the stated workload; free-host performance and venue connectivity can vary.

Evidence: [successful capacity workflow](https://github.com/execuu/halubilo_score/actions/runs/34562020074), local `output/cloud/final-capacity/load-test.json` and its per-request checkpoint. GitHub artifacts expire; the local copies are retained.

Earlier attempts are retained as failed evidence. One local runner was interrupted; another encountered local DNS failures. A first complete hosted run accepted 595 scores and failed five score-page GETs when switching to accounts whose Python HTTP connection pools had been idle for 7.5 minutes. Before the successful run, the harness was changed to close those idle pools while retaining authenticated cookies before first use. It does not retry failed requests or score submissions. No failed attempt is counted as a passing gate.

An upgrade from 1.1.0 to 1.1.1 preserved all 595 then-existing rehearsal scores, standings, account access and image bytes (`output/cloud/upgrade-persistence.json`). Hosted Chromium at 390×844 verified scoring controls, navigation, images and draft preservation across a leaderboard refresh, with no console errors or horizontal page overflow.

## Hosted backup and LAN recovery

The hosted rehearsal verified that an activity head receives 403 when attempting a correction, an administrator can correct with a reason, a stale version receives 409, and closing scoring blocks further corrections. A downloaded backup contained 30 teams, 20 activities, 600 scores, 3,164 audit records, 21 accounts and the referenced image.

Both a native SQLite restore and a new Docker volume passed integrity checks and reproduced the source standings and image bytes. The corrected score and its audit reason survived. The Docker copy was reopened with a reason and accepted score 601 while the closed cloud source remained unchanged. Restore-to-successful-continuation took **11.38 seconds** in the automated Docker drill. Loopback and the laptop's then-current LAN interface (`10.36.125.11:8083`) returned HTTP 200. This does not measure participant coordination or a physical phone on venue Wi-Fi.

Evidence: `output/cloud/recovery-result.json`, `output/cloud/docker-recovery-result.json`, and private `output/cloud/hosted-rehearsal-backup.zip`. The recovery container was stopped after the drill; its separate volume `halubilo_cloud_recovery_20260911` was retained. No original local event volume was overwritten.

## Original local release verification — 11 September 2026

## Phase status

| Phase | Status | Evidence |
| --- | --- | --- |
| Repository audit and operating model | Complete | SYSTEM_AUDIT.md; inherited runtime failure reproduced with an isolated database |
| Reproducible local/container runtime | Complete | Python 3.13.15, Gunicorn, health checks, persistent named volumes, private admin setup |
| Correctness and deployment hardening | Complete locally | 29 regression cases passed in the Python 3.13 test image with networking disabled |
| Performance and mobile/report verification | Complete locally | Fifteen-minute workload, Chromium 390x844 checks, rendered three-page A4 report |
| Backup/recovery implementation and automated drill | Complete locally | Verified restore, image equality, closed source, audited reopening and successful new submission |
| Render + Supabase deployment and hosted gates | Complete | Public HTTPS, clean admin login, private storage, persistence, 900-second capacity test and cloud-to-Docker recovery passed |
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

## Fresh event deployment

Render was switched from the disposable rehearsal project to dedicated Supabase project `halubilo-scoresheet` (`cmvpdamcnnzodvpumxsv`). Deployment `dep-dahocibm8hqs73cmu480` became live at 04:41:32 UTC on 11 September 2026, using tested application commit `f8f06286643be73842b9f41014a82a91a1403a38`. The real HTTPS administrator login, empty standings, reports, audit and backup download passed. The real administrator dashboard was also verified in mobile Chromium.

There is one administrator and no teams, activities or scores. Initial admin credentials are in private local `instance/cloud-admin-credentials.txt`; the initial backup is `backups/cloud-initial-event.zip`. Render remains on Free with automatic deployments disabled and no initial admin password in its runtime configuration. Evidence: `output/cloud/production-result.json` and `output/playwright/cloud-production-admin.png`.

## Remaining release gates

The source release manifest was verified and the PythonAnywhere preparation helper passed both fresh initialization and repeat initialization under Python 3.13 with networking disabled. The archive contains no event database or secrets. Evidence: `output/releases/native-check.json`. PythonAnywhere was not used for the final deployment. Render + Supabase passed the hosted HTTPS, persistence, workload and recovery checks above. The remaining organizer gate is testing actual scorekeeper phones and the venue router, including coordinated recovery. Free-host limits remain material; refer to DEPLOYMENT.md.
