#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-status}" in
  status)
    docker compose ps
    local_port=$(docker compose port web 8080 | awk -F: '{print $NF}')
    if [ -z "$local_port" ]; then echo 'Web service is not running.'; exit 1; fi
    curl --fail --silent --show-error "http://127.0.0.1:$local_port/healthz"
    lan_ip=$(ip -4 route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}')
    printf '\nLocal: http://localhost:%s\nLAN: http://%s:%s\n' "$local_port" "$lan_ip" "$local_port"
    curl --fail --silent --show-error "http://$lan_ip:$local_port/healthz"
    printf '\n'
    ;;
  backup)
    mkdir -p backups
    chmod 700 backups
    backup_name="halubilo-$(date -u +%Y%m%dT%H%M%SZ).zip"
    docker compose exec -T web flask --app app:create_app backup "/backups/$backup_name"
    docker compose cp "web:/backups/$backup_name" "backups/$backup_name"
    chmod 600 "backups/$backup_name"
    printf 'Local backup: backups/%s\n' "$backup_name"
    ;;
  *) echo 'Usage: bash scripts/ops.sh status|backup'; exit 2 ;;
esac
