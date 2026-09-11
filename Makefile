.PHONY: setup build init start stop restart status logs test backup admin recover assets migrate release
setup:
	python3 scripts/setup.py
build:
	docker compose build
init: setup build
	docker compose run --rm --no-deps web flask --app app:create_app migrate
start:
	docker compose up -d --wait
stop:
	docker compose stop
restart:
	docker compose up -d --force-recreate --wait
status:
	bash scripts/ops.sh status
logs:
	docker compose logs --tail=100 web
migrate:
	docker compose run --rm --no-deps web flask --app app:create_app migrate
admin:
	docker compose exec web flask --app app:create_app admin-create
recover:
	docker compose exec web flask --app app:create_app admin-recover
backup:
	bash scripts/ops.sh backup
test:
	docker build --target test -t halubilo-scoresheet:test .
	docker run --rm --network none halubilo-scoresheet:test
assets:
	npm ci
	npm run build
release:
	python3 scripts/release.py
