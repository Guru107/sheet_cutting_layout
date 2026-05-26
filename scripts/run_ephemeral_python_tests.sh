#!/usr/bin/env bash

set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCH_ROOT="${BENCH_ROOT:-$(cd "$APP_ROOT/../.." && pwd)}"
DB_ROOT_USERNAME="${DB_ROOT_USERNAME:-root}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-}"
EPHEMERAL_ADMIN_PASSWORD="${EPHEMERAL_ADMIN_PASSWORD:-admin}"
RUN_ID="${EPHEMERAL_SITE_RUN_ID:-$(date +%Y%m%d%H%M%S)-$$}"
SITE_NAME="scl-ci-${RUN_ID}.localhost"

if [ -z "$DB_ROOT_PASSWORD" ]; then
	echo "DB_ROOT_PASSWORD is required for ephemeral site creation and teardown." >&2
	exit 1
fi

cleanup() {
	local exit_code=$?
	set +e
	if [ -n "${SITE_NAME:-}" ] && [ -d "$BENCH_ROOT/sites/$SITE_NAME" ]; then
		echo "Dropping ephemeral site $SITE_NAME"
		cd "$BENCH_ROOT"
		bench drop-site "$SITE_NAME" --force --no-backup --db-root-username "$DB_ROOT_USERNAME" --db-root-password "$DB_ROOT_PASSWORD"
	fi
	exit "$exit_code"
}

trap cleanup EXIT

cd "$BENCH_ROOT"
bench pip install pytest hypothesis

bench new-site "$SITE_NAME" --db-root-username "$DB_ROOT_USERNAME" --db-root-password "$DB_ROOT_PASSWORD" --admin-password "$EPHEMERAL_ADMIN_PASSWORD"
bench --site "$SITE_NAME" install-app erpnext
bench --site "$SITE_NAME" install-app sheet_cutting_layout
bench build --app sheet_cutting_layout
bench --site "$SITE_NAME" execute erpnext.setup.setup_wizard.operations.install_fixtures.install --args '["India"]'
bench --site "$SITE_NAME" execute sheet_cutting_layout.tests.test_setup.before_tests
bench --site "$SITE_NAME" set-config allow_tests true

run_tests_cmd=(bench --site "$SITE_NAME" run-tests --app sheet_cutting_layout)

if [ "$#" -gt 0 ]; then
	run_tests_cmd+=(--module "$1")
fi

"${run_tests_cmd[@]}"
