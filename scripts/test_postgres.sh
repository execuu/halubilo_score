#!/usr/bin/env bash
set -euo pipefail
# Fixed, dedicated test project: never connects to the event's volumes or network.
trap 'docker compose -p halubilo-cloud-tests -f compose.tests.yaml down --volumes' EXIT
docker compose -p halubilo-cloud-tests -f compose.tests.yaml up --build --abort-on-container-exit --exit-code-from tests
