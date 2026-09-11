# Reproduce the event workload

Use a separate, empty rehearsal database. Never run the seed or load script against real event data. The load script requires explicit rehearsal confirmation and refuses a nonempty or unexpected team fixture.

```bash
python3 scripts/setup.py --rehearsal
# Choose a NEW project name on subsequent runs to preserve earlier evidence.
docker compose --env-file .env.rehearsal -p halubilo-rehearsal \
  -f compose.yaml -f compose.rehearsal.yaml run --rm --no-deps web \
  flask --app app:create_app migrate
docker compose --env-file .env.rehearsal -p halubilo-rehearsal \
  -f compose.yaml -f compose.rehearsal.yaml run --rm --no-deps web \
  python scripts/seed_rehearsal.py
docker compose --env-file .env.rehearsal -p halubilo-rehearsal \
  -f compose.yaml -f compose.rehearsal.yaml up -d --wait
.venv/bin/python scripts/load_test.py --confirm-rehearsal \
  --url http://127.0.0.1:8081 --seconds 900 --p95-ms 1000 \
  --output output/load-test.json
```

Install `requirements-dev.txt` in `.venv` for the host load generator. The private `.env.rehearsal` contains independent secrets and temporary account credentials. It is not included in Git or release archives. Twenty assigned accounts cover twenty activities; ten concurrent scorekeeper threads each handle two activity accounts in sequence.

The test submits exactly 600 unique team/activity scores over fifteen minutes. Fifty viewer sessions poll every ten seconds, for 4,500 leaderboard requests. It checks final counts, independently calculated totals and ranks, unexpected HTTP statuses, and p95 latency. The request pattern includes ten simultaneous submissions each interval, rather than a single sequential writer.

For the online pilot, use the private hosting rehearsal credentials via `--env-file`, the HTTPS hostname via `--url`, and `--p95-ms 2000`. The local script must be able to reach the host. Check provider policies and use this finite rehearsal, not persistent synthetic keep-alive traffic.

Stop the rehearsal when finished:

```bash
docker compose --env-file .env.rehearsal -p halubilo-rehearsal \
  -f compose.yaml -f compose.rehearsal.yaml stop
```

The previous run's volume intentionally remains intact. Use a new project name/port for another fresh run, or explicitly retire only the known disposable rehearsal data after exporting the evidence. Do not delete the real `halubilo_event_data` volume.
