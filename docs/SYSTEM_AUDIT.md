# Inherited system audit

The inherited repository was a small Flask application last changed in August 2025. It used Flask-Login, Flask-SQLAlchemy, Flask-WTF, SQLite and server-rendered Tailwind templates. There were no automated tests or container definitions. This checkout contained no saved database or team images.

The intended workflow was administrator setup of teams/activities/users, activity-head score entry, and publicly visible summed team standings. Editing scores was admin-only even though comments suggested otherwise. Every submitted row was summed, so repeated entries inflated totals. There were no rounds, weights, independent judges, event history, audit trail, or automatic offline synchronization.

## Confirmed baseline failures

The unmodified module failed to import because `email-validator` was absent from requirements. A disposable check temporarily supplied that dependency and isolated the database in memory; no inherited data was touched.

| Check | Inherited result | Implemented behavior |
| --- | --- | --- |
| Fresh WSGI request | Missing team table; initialization only under `__main__` | Explicit versioned migration and readiness check |
| Score 0 | Rejected | Accepted and counted as submitted |
| Score 101 for maximum 100 | Accepted | Rejected before write; database trigger also enforces ceiling |
| Repeated team/activity submission | Multiple rows accumulated | One unique final score; duplicate/conflicting requests rejected |
| Unassigned user submission | Allowed for any activity | Denied until assigned |
| Score reset without CSRF | Succeeded | All state changes require CSRF and POST |
| Corrections | No reason/history or stale-edit protection | Admin reason, atomic audit entry, checked version |
| Tied totals | Distinct ranks from row order | Shared competition rank |
| Leaderboard with 21 teams | 22 database queries | Two queries including event status, independent of team count |
| Secrets / administrator setup | Hardcoded signing key and default password | Environment secret and explicit private account creation |
| Offline venue styling | External Tailwind CDN required | Locally compiled assets |
| Migration helper | Looked for database in the wrong directory | Uses configured database and refuses unversioned legacy data |
| Navigation on phones | Desktop links hidden without a mobile menu | Accessible expandable mobile navigation |

The previous README included claims that did not match the implementation, such as complete score-bound validation and deployment readiness. It also suggested deleting the database during troubleshooting. The replacement documentation uses backup/restore and explicitly separates local verification from hosting approval.

## Scope of this release

One fresh event per database; one whole-number final score per team/activity; raw-point summation; equal totals share rank. Admin-only corrections have a required reason and retained history. Activity heads enter scores only for their assignment. Cloud-to-LAN recovery is a coordinated manual restore, with reconciliation from activity worksheets. Existing organizer databases must be preserved separately rather than silently imported or reset.
