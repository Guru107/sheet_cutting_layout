#!/usr/bin/env bash
set -uo pipefail

APP="sheet_cutting_layout"
THRESHOLD="96"
PYTHON_BIN="${PYTHON:-python}"
APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

usage() {
	printf 'Usage: %s [--bench all|bench15|bench16] [--skip-python] [--skip-e2e]\n' "$0" >&2
}

expand_user_path() {
	local path="$1"
	case "$path" in
		"~")
			printf '%s\n' "$HOME"
			;;
		"~/"*)
			printf '%s/%s\n' "$HOME" "${path#"~/"}"
			;;
		*)
			printf '%s\n' "$path"
			;;
	esac
}

bench_root() {
	local env_name="$1"
	local label="$2"
	local configured="${!env_name:-}"
	local documented="$HOME/Workspace/$label"

	if [[ -n "$configured" ]]; then
		expand_user_path "$configured"
	elif [[ -e "$documented" ]]; then
		printf '%s\n' "$documented"
	else
		printf '/root/workspace/%s\n' "$label"
	fi
}

BENCH15_ROOT="$(bench_root SCL_BENCH15_ROOT bench15)"
BENCH16_ROOT="$(bench_root SCL_BENCH16_ROOT bench16)"

bench_root_for() {
	case "$1" in
		bench15) printf '%s\n' "$BENCH15_ROOT" ;;
		bench16) printf '%s\n' "$BENCH16_ROOT" ;;
	esac
}

bench_site_for() {
	case "$1" in
		bench15) printf '%s\n' "development.localhost" ;;
		bench16) printf '%s\n' "frappe16.localhost" ;;
	esac
}

print_command() {
	local cwd="$1"
	shift
	printf '\n$ cd %s &&' "$cwd"
	printf ' %q' "$@"
	printf '\n'
}

preflight() {
	local label="$1"
	local root site failed=0
	root="$(bench_root_for "$label")"
	site="$(bench_site_for "$label")"

	if [[ ! -d "$root" ]]; then
		printf '%s: bench root not found: %s\n' "$label" "$root" >&2
		failed=1
	fi
	if [[ ! -d "$root/sites/$site" ]]; then
		printf '%s: site not found: %s\n' "$label" "$site" >&2
		failed=1
	fi
	if [[ ! -d "$root/apps/$APP" ]]; then
		printf '%s: app is not linked under %s\n' "$label" "$root/apps/$APP" >&2
		failed=1
	fi
	return "$failed"
}

coverage_xml_path() {
	local root="$1"
	if [[ -e "$root/sites/coverage.xml" ]]; then
		printf '%s\n' "$root/sites/coverage.xml"
	elif [[ -e "$root/coverage.xml" ]]; then
		printf '%s\n' "$root/coverage.xml"
	else
		printf '%s\n' "$root/sites/coverage.xml"
	fi
}

new_run_id() {
	local uuid
	if [[ -r /proc/sys/kernel/random/uuid ]]; then
		uuid="$(< /proc/sys/kernel/random/uuid)"
		printf '%s\n' "${uuid//-/}"
	else
		printf '%s%s\n' "$(date +%s%N)" "$$"
	fi
}

run_python_gate() {
	local label="$1"
	local root result_dir xml_copy summary xml_path code
	root="$(bench_root_for "$label")"
	result_dir="$APP_ROOT/coverage-results/python"
	xml_copy="$result_dir/$label-coverage.xml"
	summary="$result_dir/$label-summary.json"
	mkdir -p "$result_dir" || return 2
	rm -f "$xml_copy" "$summary"

	rm -f "$root/sites/coverage.xml" "$root/coverage.xml"

	local command=(bench --site "$(bench_site_for "$label")" run-tests --app "$APP" --coverage)
	print_command "$root" "${command[@]}"
	(cd "$root" && "${command[@]}")
	code=$?
	if (( code != 0 )); then
		printf '%s: Python tests failed before coverage could be checked\n' "$label" >&2
		return "$code"
	fi

	xml_path="$(coverage_xml_path "$root")"
	if [[ ! -e "$xml_path" ]]; then
		printf '%s: expected coverage XML not found at %s\n' "$label" "$xml_path" >&2
		return 2
	fi
	cp "$xml_path" "$xml_copy" || {
		printf '%s: failed to copy coverage XML to %s\n' "$label" "$xml_copy" >&2
		return 2
	}

	local check_command=(
		"$PYTHON_BIN"
		"$APP_ROOT/scripts/check_python_coverage.py"
		--xml "$xml_copy"
		--threshold "$THRESHOLD"
		--report "$summary"
	)
	print_command "$APP_ROOT" "${check_command[@]}"
	(cd "$APP_ROOT" && "${check_command[@]}")
	return $?
}

run_e2e_gate() {
	local label="$1"
	local root result_dir report run_id code
	root="$(bench_root_for "$label")"
	result_dir="$APP_ROOT/coverage-results/e2e"
	report="$result_dir/$label-flow-coverage.json"
	mkdir -p "$result_dir"
	rm -f "$report"
	run_id="$(new_run_id)"

	local command=(bench --site "$(bench_site_for "$label")" run-ui-tests --headless "$APP")
	print_command "$root" "${command[@]}"
	(
		cd "$root" &&
			SCL_FLOW_COVERAGE_OUTPUT="$report" \
			SCL_FLOW_COVERAGE_RUN_ID="$run_id" \
			"${command[@]}"
	)
	code=$?
	if (( code != 0 )); then
		printf '%s: Cypress tests failed before flow coverage could be checked\n' "$label" >&2
		return "$code"
	fi

	local check_command=(
		"$PYTHON_BIN"
		"$APP_ROOT/scripts/check_e2e_flow_coverage.py"
		--report "$report"
		--threshold "$THRESHOLD"
		--run-id "$run_id"
	)
	print_command "$APP_ROOT" "${check_command[@]}"
	(cd "$APP_ROOT" && "${check_command[@]}")
	return $?
}

bench="all"
skip_python=0
skip_e2e=0

while (($#)); do
	case "$1" in
		--bench)
			if (($# < 2)); then
				printf '%s\n' "--bench requires a value" >&2
				usage
				exit 2
			fi
			bench="$2"
			shift 2
			;;
		--bench=*)
			bench="${1#--bench=}"
			shift
			;;
		--skip-python)
			skip_python=1
			shift
			;;
		--skip-e2e)
			skip_e2e=1
			shift
			;;
		-h|--help)
			usage
			exit 0
			;;
		*)
			printf 'Unknown argument: %s\n' "$1" >&2
			usage
			exit 2
			;;
	esac
done

case "$bench" in
	all) targets=(bench15 bench16) ;;
	bench15|bench16) targets=("$bench") ;;
	*)
		printf 'invalid --bench value: %s\n' "$bench" >&2
		usage
		exit 2
		;;
esac

if (( skip_python == 1 && skip_e2e == 1 )); then
	printf '%s\n' "At least one coverage gate must run; do not pass both --skip-python and --skip-e2e" >&2
	exit 2
fi

preflight_failed=0
for target in "${targets[@]}"; do
	if ! preflight "$target"; then
		preflight_failed=1
	fi
done
if (( preflight_failed != 0 )); then
	exit 2
fi

result_benches=()
result_gates=()
result_codes=()

for target in "${targets[@]}"; do
	if (( skip_python == 0 )); then
		run_python_gate "$target"
		code=$?
		result_benches+=("$target")
		result_gates+=("python")
		result_codes+=("$code")
	fi
	if (( skip_e2e == 0 )); then
		run_e2e_gate "$target"
		code=$?
		result_benches+=("$target")
		result_gates+=("e2e")
		result_codes+=("$code")
	fi
done

printf '\nCoverage gate summary\n'
for index in "${!result_codes[@]}"; do
	code="${result_codes[$index]}"
	if (( code == 0 )); then
		status="PASS"
	else
		status="FAIL($code)"
	fi
	printf '%-7s %-6s %s\n' "${result_benches[$index]}" "${result_gates[$index]}" "$status"
done

for code in "${result_codes[@]}"; do
	if (( code == 2 )); then
		exit 2
	fi
done
for code in "${result_codes[@]}"; do
	if (( code != 0 )); then
		exit 1
	fi
done
exit 0
