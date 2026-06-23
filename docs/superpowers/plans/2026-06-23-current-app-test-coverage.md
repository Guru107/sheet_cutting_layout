# Current App Test Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce above-96% Python and Desk JS/E2E coverage for current live Sheet Cutting Layout behavior on bench15 and bench16.

**Architecture:** Use Frappe's native `bench run-tests --coverage` and `bench run-ui-tests` commands, then add small repo-owned checkers that parse the resulting Python coverage XML and Cypress flow coverage JSON. Remove stale recursive/`child_layout` tests from the active suite, mark only current E2E flows, and keep the dual-bench runner conservative: it reports setup blockers and never runs `migrate`, `build`, or destructive cleanup.

**Tech Stack:** Frappe v15/v16 bench commands, Python stdlib XML/JSON parsing, Cypress task hooks, existing Frappe `FrappeTestCase` tests.

---

## File Structure

- Delete: `cypress/integration/sheet_cutting_layout_recursive_end_piece.js`  
  Removed feature E2E; references `child_layout`.
- Delete: `cypress/integration/sheet_cutting_layout_export_recursion.js`  
  Removed feature E2E; references recursive export and cascade retirement.
- Delete: `sheet_cutting_layout/tests/test_recursive_end_piece.py`  
  Cosmetic absence-only schema test for removed `child_layout`.
- Create: `scripts/check_python_coverage.py`  
  Parse Frappe `coverage.xml`, apply project-owned exclusions, and fail when coverage is at or below 96%.
- Create: `scripts/check_e2e_flow_coverage.py`  
  Parse the current-flow manifest and Cypress run report, fail on unknown IDs or at-or-below-96% flow coverage.
- Create: `scripts/run_current_coverage_gates.py`  
  Run all four gates: Python v15, Python v16, E2E v15, E2E v16.
- Create: `cypress/support/current_flows.json`  
  Current live Desk flow manifest.
- Modify: `cypress.config.js`  
  Add `setupNodeEvents` with a tiny `markFlow` task.
- Modify: `cypress/support/e2e.js`  
  Add `cy.markFlow(id)` and validate IDs against `current_flows.json`.
- Modify: current Cypress specs under `cypress/integration/`  
  Mark current live flow IDs after real assertions pass.
- Modify: `.gitignore`  
  Ignore `coverage-results/`.
- Create: `docs/current-app-test-coverage.md`  
  Document commands, reports, and flow-ID rules.
- Modify: `AGENTS.md`  
  Replace the stale "No test suite exists yet" sentence with the dual-bench coverage gate.

## Task 1: Remove Stale Removed-Feature Tests

**Files:**
- Delete: `cypress/integration/sheet_cutting_layout_recursive_end_piece.js`
- Delete: `cypress/integration/sheet_cutting_layout_export_recursion.js`
- Delete: `sheet_cutting_layout/tests/test_recursive_end_piece.py`

- [ ] **Step 1: Verify the stale references**

Run:

```bash
rg -n "child_layout|recursive end-piece|export \\+ recursion|cascade" \
  cypress/integration sheet_cutting_layout/tests
```

Expected before deletion: references in the two Cypress specs and the cosmetic Python schema test.

- [ ] **Step 2: Delete only stale tests**

Run:

```bash
git rm \
  cypress/integration/sheet_cutting_layout_recursive_end_piece.js \
  cypress/integration/sheet_cutting_layout_export_recursion.js \
  sheet_cutting_layout/tests/test_recursive_end_piece.py
```

- [ ] **Step 3: Verify no active test still targets removed behavior**

Run:

```bash
rg -n "child_layout|recursive end-piece|export \\+ recursion|cascade" \
  cypress/integration sheet_cutting_layout/tests
```

Expected: no output.

- [ ] **Step 4: Run the currently affected lightweight checks**

Run:

```bash
cd /root/workspace/bench15
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: OK. If the site reports migration or fixture setup blockers, stop and report the exact blocker.

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "test: remove stale child layout coverage"
```

## Task 2: Add Python Coverage Checker

**Files:**
- Create: `scripts/check_python_coverage.py`

- [ ] **Step 1: Create the checker**

Create `scripts/check_python_coverage.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_THRESHOLD = 96.0

EXCLUDED_PATTERNS = (
	"sheet_cutting_layout/__init__.py",
	"sheet_cutting_layout/**/__init__.py",
	"sheet_cutting_layout/config/*",
	"sheet_cutting_layout/patches/*",
	"sheet_cutting_layout/tests/*",
	"sheet_cutting_layout/**/doctype/*/*_dashboard.py",
)

PASS_THROUGH_DOCTYPES = (
	"sheet_cutting_layout/sheet_cutting_layout/doctype/layout_approval_snapshot/layout_approval_snapshot.py",
	"sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.py",
	"sheet_cutting_layout/sheet_cutting_layout/doctype/layout_finished_part/layout_finished_part.py",
	"sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout_settings/sheet_cutting_layout_settings.py",
)


def _matches(filename: str, patterns: tuple[str, ...]) -> bool:
	return any(fnmatch.fnmatch(filename, pattern) for pattern in patterns)


def _is_excluded(filename: str) -> bool:
	return filename in PASS_THROUGH_DOCTYPES or _matches(filename, EXCLUDED_PATTERNS)


def _line_numbers(class_node: ET.Element) -> tuple[int, int, list[int]]:
	valid = 0
	covered = 0
	missing: list[int] = []
	lines = class_node.find("lines")
	for line in lines.findall("line") if lines is not None else []:
		valid += 1
		number = int(line.attrib["number"])
		if int(line.attrib.get("hits", "0")) > 0:
			covered += 1
		else:
			missing.append(number)
	return valid, covered, missing


def summarize(xml_path: Path) -> dict[str, object]:
	root = ET.parse(xml_path).getroot()
	files: list[dict[str, object]] = []
	total_valid = 0
	total_covered = 0

	for class_node in root.findall(".//class"):
		filename = class_node.attrib["filename"]
		if _is_excluded(filename):
			continue
		valid, covered, missing = _line_numbers(class_node)
		if valid == 0:
			continue
		total_valid += valid
		total_covered += covered
		files.append(
			{
				"file": filename,
				"valid": valid,
				"covered": covered,
				"missing": missing,
				"percent": round(covered / valid * 100, 2),
			}
		)

	percent = 100.0 if total_valid == 0 else total_covered / total_valid * 100
	return {
		"percent": round(percent, 2),
		"covered": total_covered,
		"valid": total_valid,
		"files": sorted(files, key=lambda item: (item["percent"], item["file"])),
	}


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--xml", required=True, type=Path)
	parser.add_argument("--threshold", default=DEFAULT_THRESHOLD, type=float)
	parser.add_argument("--report", type=Path)
	args = parser.parse_args()

	if not args.xml.exists():
		print(f"coverage XML not found: {args.xml}", file=sys.stderr)
		return 2

	summary = summarize(args.xml)
	if args.report:
		args.report.parent.mkdir(parents=True, exist_ok=True)
		args.report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

	print(f"Python coverage: {summary['percent']}% ({summary['covered']}/{summary['valid']} lines)")
	if float(summary["percent"]) <= args.threshold:
		print(f"Coverage must be above {args.threshold}%. Lowest files:", file=sys.stderr)
		for item in summary["files"][:10]:
			missing = ",".join(str(line) for line in item["missing"][:20])
			print(f"  {item['percent']}% {item['file']} missing {missing}", file=sys.stderr)
		return 1
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
```

- [ ] **Step 2: Make it executable**

Run:

```bash
chmod +x scripts/check_python_coverage.py
```

- [ ] **Step 3: Check the existing bench15 coverage XML if present**

Run:

```bash
python scripts/check_python_coverage.py \
  --xml /root/workspace/bench15/sites/coverage.xml \
  --threshold 96 \
  --report coverage-results/python/bench15-summary.json
```

Expected when the XML exists and current coverage is sufficient: command exits 0 and prints `Python coverage: ...%`.
Expected when the XML is stale or absent: the command exits nonzero with a clear file or coverage message.

- [ ] **Step 4: Commit**

```bash
git add scripts/check_python_coverage.py
git commit -m "test: add python coverage checker"
```

## Task 3: Add Current E2E Flow Coverage Plumbing

**Files:**
- Create: `cypress/support/current_flows.json`
- Create: `scripts/check_e2e_flow_coverage.py`
- Modify: `cypress.config.js`
- Modify: `cypress/support/e2e.js`

- [ ] **Step 1: Add the current-flow manifest**

Create `cypress/support/current_flows.json`:

```json
[
  {
    "id": "consumption.balanced-layout-calculates-and-saves",
    "label": "Balanced layout calculations persist from the Desk form"
  },
  {
    "id": "export.single-layout-downloads-xlsx",
    "label": "Single-layout IATF export downloads a non-empty XLSX"
  },
  {
    "id": "lh-rh.toggle-fields",
    "label": "LH/RH toggle defaults and clears paired fields"
  },
  {
    "id": "lh-rh.release-two-boms",
    "label": "LH/RH release creates separate active BOMs for both parts"
  },
  {
    "id": "release.single-part-generates-bom",
    "label": "Release creates an active Shearing BOM for the finished part"
  },
  {
    "id": "release.new-version-draft",
    "label": "Released layout can create the next draft revision"
  },
  {
    "id": "workflow.reject-returns-to-draft",
    "label": "Rejected in-review layout returns to Draft"
  }
]
```

- [ ] **Step 2: Add the E2E checker**

Create `scripts/check_e2e_flow_coverage.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_THRESHOLD = 96.0


def _read_json(path: Path) -> object:
	if not path.exists():
		raise FileNotFoundError(path)
	return json.loads(path.read_text())


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--manifest", default=Path("cypress/support/current_flows.json"), type=Path)
	parser.add_argument("--report", required=True, type=Path)
	parser.add_argument("--threshold", default=DEFAULT_THRESHOLD, type=float)
	args = parser.parse_args()

	try:
		manifest = _read_json(args.manifest)
		report = _read_json(args.report)
	except FileNotFoundError as error:
		print(f"missing flow coverage file: {error.filename}", file=sys.stderr)
		return 2

	flow_ids = [str(flow["id"]) for flow in manifest]
	flow_id_set = set(flow_ids)
	covered = set(str(flow_id) for flow_id in report.get("covered", []))
	unknown = sorted(covered - flow_id_set)
	if unknown:
		print("unknown or stale E2E flow IDs:", file=sys.stderr)
		for flow_id in unknown:
			print(f"  {flow_id}", file=sys.stderr)
		return 1

	missing = [flow_id for flow_id in flow_ids if flow_id not in covered]
	total = len(flow_ids)
	covered_count = total - len(missing)
	percent = 100.0 if total == 0 else covered_count / total * 100

	print(f"E2E flow coverage: {percent:.2f}% ({covered_count}/{total} flows)")
	if percent <= args.threshold:
		print(f"Coverage must be above {args.threshold}%. Missing flows:", file=sys.stderr)
		for flow_id in missing:
			print(f"  {flow_id}", file=sys.stderr)
		return 1
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
```

- [ ] **Step 3: Make the checker executable**

Run:

```bash
chmod +x scripts/check_e2e_flow_coverage.py
```

- [ ] **Step 4: Add Cypress node event plumbing**

Modify `cypress.config.js` so it reads:

```javascript
const fs = require("fs");
const path = require("path");

const currentFlows = require("./cypress/support/current_flows.json");

function writeFlowReport(outputPath, covered) {
	const flowIds = currentFlows.map((flow) => flow.id);
	const payload = {
		total: flowIds.length,
		covered: Array.from(covered).sort(),
		missing: flowIds.filter((flowId) => !covered.has(flowId)),
	};
	fs.mkdirSync(path.dirname(outputPath), { recursive: true });
	fs.writeFileSync(outputPath, `${JSON.stringify(payload, null, 2)}\n`);
}

module.exports = {
	defaultCommandTimeout: 20000,
	pageLoadTimeout: 15000,
	video: true,
	viewportHeight: 960,
	viewportWidth: 1400,
	retries: {
		runMode: 1,
		openMode: 1,
	},
	env: {
		adminPassword: "123",
	},
	e2e: {
		baseUrl: "http://localhost:8002",
		specPattern: ["./cypress/integration/*.js"],
		testIsolation: true,
		setupNodeEvents(on) {
			const flowIds = new Set(currentFlows.map((flow) => flow.id));
			const covered = new Set();
			const outputPath =
				process.env.SCL_FLOW_COVERAGE_OUTPUT ||
				path.join("cypress", "results", "current-flow-coverage.json");

			writeFlowReport(outputPath, covered);

			on("task", {
				markFlow(flowId) {
					if (!flowIds.has(flowId)) {
						throw new Error(`Unknown current E2E flow ID: ${flowId}`);
					}
					covered.add(flowId);
					writeFlowReport(outputPath, covered);
					return null;
				},
			});

			on("after:run", () => {
				writeFlowReport(outputPath, covered);
			});
		},
	},
};
```

- [ ] **Step 5: Add `cy.markFlow`**

Append this to `cypress/support/e2e.js`:

```javascript
const currentFlows = require("./current_flows.json");
const currentFlowIds = new Set(currentFlows.map((flow) => flow.id));

Cypress.Commands.add("markFlow", (flowId) => {
	expect(currentFlowIds.has(flowId), `current E2E flow ID: ${flowId}`).to.equal(true);
	return cy.task("markFlow", flowId, { log: false });
});
```

- [ ] **Step 6: Validate the checker failure path before any specs mark flows**

Run:

```bash
mkdir -p cypress/results
printf '{"covered":[]}\n' > cypress/results/current-flow-coverage.json
python scripts/check_e2e_flow_coverage.py \
  --report cypress/results/current-flow-coverage.json \
  --threshold 96
```

Expected: FAIL and list all seven current flow IDs as missing.

- [ ] **Step 7: Commit**

```bash
git add cypress.config.js cypress/support/e2e.js cypress/support/current_flows.json scripts/check_e2e_flow_coverage.py
git commit -m "test: add current e2e flow coverage"
```

## Task 4: Mark Current Cypress Flows

**Files:**
- Modify: `cypress/integration/sheet_cutting_layout_consumption.js`
- Modify: `cypress/integration/sheet_cutting_layout_export.js`
- Modify: `cypress/integration/sheet_cutting_layout_lh_rh.js`
- Modify: `cypress/integration/sheet_cutting_layout_release.js`

- [ ] **Step 1: Mark the consumption flow**

In `cypress/integration/sheet_cutting_layout_consumption.js`, add this line at the end of the existing test, after `cy.contains('[data-fieldname="status"]', "Draft");`:

```javascript
		cy.markFlow("consumption.balanced-layout-calculates-and-saves");
```

- [ ] **Step 2: Mark the single-layout export flow**

In `cypress/integration/sheet_cutting_layout_export.js`, add this line inside the `cy.request(...).then((response) => { ... })` block, after `expect(response.body.slice(0, 2)).to.equal("PK");`:

```javascript
				cy.markFlow("export.single-layout-downloads-xlsx");
```

- [ ] **Step 3: Mark the LH/RH flows**

In `cypress/integration/sheet_cutting_layout_lh_rh.js`, add this line after the unchecked assertions in the toggle test:

```javascript
			cy.markFlow("lh-rh.toggle-fields");
```

In the release test, add this after all BOM assertions have been queued:

```javascript
				cy.markFlow("lh-rh.release-two-boms");
```

- [ ] **Step 4: Mark release and new-version flows**

In `cypress/integration/sheet_cutting_layout_release.js`, add this line after the BOM detail assertions:

```javascript
					cy.markFlow("release.single-part-generates-bom");
```

Add this line after `cy.get('[data-fieldname="revision_no"] input').should("have.value", "2");`:

```javascript
			cy.markFlow("release.new-version-draft");
```

- [ ] **Step 5: Add current rejection flow**

In `cypress/integration/sheet_cutting_layout_release.js`, add a second layout code near the other constants:

```javascript
	const rejectLayoutCode = `SCLREJECTCY${suffix}`;
```

Append this test inside the existing `describe` block:

```javascript
	it("returns a submitted-for-check layout to Draft when rejected", { retries: 0 }, () => {
		cy.call("frappe.client.insert", {
			doc: {
				doctype: "Sheet Cutting Layout",
				layout_code: rejectLayoutCode,
				project: projectName,
				revision_no: 1,
				is_active: 0,
				status: "Draft",
				raw_material_item: rawMaterialItem,
				process_scrap_item: processScrapItem,
				sheet_thickness_mm: 2,
				sheet_width_mm: 1000,
				sheet_length_mm: 2000,
				weight_per_sheet_kg: 31.44,
				strip_thickness_mm: 2,
				strip_width_mm: 1000,
				strip_length_mm: 1000,
				weight_of_strip_kg: 15.72,
				parts_per_strip: 1,
				no_of_strips: 2,
				parts_per_sheet: 2,
				finished_part_code: finishedPartItem,
				net_weight_per_part_kg: 15.52,
				gross_weight_per_part_kg: 15.72,
				scrap_weight_per_part_kg: 0.2,
				finished_parts: [
					{
						doctype: "Layout Finished Part",
						finished_part_item: finishedPartItem,
						parts_per_sheet: 2,
						net_weight_per_part_kg: 15.52,
						gross_weight_per_part_kg: 15.72,
						scrap_weight_per_part_kg: 0.2,
					},
				],
			},
		});
		cy.visit(`/app/sheet-cutting-layout/${rejectLayoutCode}`);
		cy.contains('[data-fieldname="status"]', "Draft");

		runWorkflowAction("Submit for Check", "Submitted for Check");
		runWorkflowAction("Reject", "Draft");

		cy.contains('[data-fieldname="status"]', "Draft");
		cy.markFlow("workflow.reject-returns-to-draft");
	});
```

- [ ] **Step 6: Run a syntax check**

Run:

```bash
node -c cypress.config.js
for file in cypress/integration/*.js cypress/support/e2e.js; do node -c "$file"; done
```

Expected: no output and exit 0.

- [ ] **Step 7: Commit**

```bash
git add cypress/integration cypress.config.js cypress/support/e2e.js
git commit -m "test: mark current e2e flows"
```

## Task 5: Add Dual-Bench Coverage Gate Runner

**Files:**
- Create: `scripts/run_current_coverage_gates.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create the runner**

Create `scripts/run_current_coverage_gates.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

APP = "sheet_cutting_layout"
APP_ROOT = Path(__file__).resolve().parents[1]
THRESHOLD = "96"


@dataclass(frozen=True)
class BenchTarget:
	label: str
	root: Path
	site: str


BENCHES = (
	BenchTarget("bench15", Path("/root/workspace/bench15"), "development.localhost"),
	BenchTarget("bench16", Path("/root/workspace/bench16"), "frappe16.localhost"),
)


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> int:
	print(f"\n$ cd {cwd} && {' '.join(command)}")
	completed = subprocess.run(command, cwd=cwd, env=env)
	return completed.returncode


def preflight(bench: BenchTarget) -> list[str]:
	errors: list[str] = []
	if not bench.root.exists():
		errors.append(f"{bench.label}: bench root not found: {bench.root}")
	if not (bench.root / "sites" / bench.site).exists():
		errors.append(f"{bench.label}: site not found: {bench.site}")
	if not (bench.root / "apps" / APP).exists():
		errors.append(f"{bench.label}: app is not linked under {bench.root / 'apps' / APP}")
	return errors


def coverage_xml_path(bench: BenchTarget) -> Path:
	candidates = (
		bench.root / "sites" / "coverage.xml",
		bench.root / "coverage.xml",
	)
	for candidate in candidates:
		if candidate.exists():
			return candidate
	return candidates[0]


def run_python_gate(bench: BenchTarget) -> int:
	result_dir = APP_ROOT / "coverage-results" / "python"
	result_dir.mkdir(parents=True, exist_ok=True)
	xml_copy = result_dir / f"{bench.label}-coverage.xml"
	summary = result_dir / f"{bench.label}-summary.json"

	code = run(
		["bench", "--site", bench.site, "run-tests", "--app", APP, "--coverage"],
		cwd=bench.root,
	)
	if code != 0:
		print(f"{bench.label}: Python tests failed before coverage could be checked", file=sys.stderr)
		return code

	xml_path = coverage_xml_path(bench)
	if not xml_path.exists():
		print(f"{bench.label}: expected coverage XML not found at {xml_path}", file=sys.stderr)
		return 2
	shutil.copyfile(xml_path, xml_copy)
	return run(
		[
			sys.executable,
			str(APP_ROOT / "scripts" / "check_python_coverage.py"),
			"--xml",
			str(xml_copy),
			"--threshold",
			THRESHOLD,
			"--report",
			str(summary),
		],
		cwd=APP_ROOT,
	)


def run_e2e_gate(bench: BenchTarget) -> int:
	result_dir = APP_ROOT / "coverage-results" / "e2e"
	result_dir.mkdir(parents=True, exist_ok=True)
	report = result_dir / f"{bench.label}-flow-coverage.json"
	env = os.environ.copy()
	env["SCL_FLOW_COVERAGE_OUTPUT"] = str(report)

	code = run(
		["bench", "--site", bench.site, "run-ui-tests", "--headless", APP],
		cwd=bench.root,
		env=env,
	)
	if code != 0:
		print(f"{bench.label}: Cypress tests failed before flow coverage could be checked", file=sys.stderr)
		return code

	return run(
		[
			sys.executable,
			str(APP_ROOT / "scripts" / "check_e2e_flow_coverage.py"),
			"--report",
			str(report),
			"--threshold",
			THRESHOLD,
		],
		cwd=APP_ROOT,
	)


def selected_benches(name: str) -> tuple[BenchTarget, ...]:
	if name == "all":
		return BENCHES
	return tuple(bench for bench in BENCHES if bench.label == name)


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--bench", choices=("all", "bench15", "bench16"), default="all")
	parser.add_argument("--skip-python", action="store_true")
	parser.add_argument("--skip-e2e", action="store_true")
	args = parser.parse_args()

	targets = selected_benches(args.bench)
	errors = [error for bench in targets for error in preflight(bench)]
	if errors:
		for error in errors:
			print(error, file=sys.stderr)
		return 2

	results: list[tuple[str, str, int]] = []
	for bench in targets:
		if not args.skip_python:
			results.append((bench.label, "python", run_python_gate(bench)))
		if not args.skip_e2e:
			results.append((bench.label, "e2e", run_e2e_gate(bench)))

	print("\nCoverage gate summary")
	for bench_label, gate, code in results:
		status = "PASS" if code == 0 else f"FAIL({code})"
		print(f"{bench_label:7} {gate:6} {status}")

	return 1 if any(code != 0 for _bench, _gate, code in results) else 0


if __name__ == "__main__":
	raise SystemExit(main())
```

- [ ] **Step 2: Make it executable**

Run:

```bash
chmod +x scripts/run_current_coverage_gates.py
```

- [ ] **Step 3: Ignore generated coverage reports**

Append this line to `.gitignore` if it is not already present:

```gitignore
coverage-results/
```

- [ ] **Step 4: Run runner preflight with Python only on bench15**

Run:

```bash
python scripts/run_current_coverage_gates.py --bench bench15 --skip-e2e
```

Expected: Python tests run through bench15 and Python coverage is above 96%. If the command fails because the site needs migration or fixture setup, report the exact bench output and run the printed setup command only after user approval.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_current_coverage_gates.py .gitignore
git commit -m "test: add dual bench coverage gate runner"
```

## Task 6: Document The Coverage Gate

**Files:**
- Create: `docs/current-app-test-coverage.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Add coverage documentation**

Create `docs/current-app-test-coverage.md`:

````markdown
# Current App Test Coverage

The Sheet Cutting Layout coverage gate measures current live behavior only.
Removed `child_layout` and recursive end-piece flows are not part of the active test matrix.

## Full Gate

Run from the app repo:

```bash
python scripts/run_current_coverage_gates.py
```

The command runs four independent gates:

1. bench15 Python coverage on `development.localhost`
2. bench16 Python coverage on `frappe16.localhost`
3. bench15 Desk JS/E2E flow coverage on `development.localhost`
4. bench16 Desk JS/E2E flow coverage on `frappe16.localhost`

Each gate must be above 96%. A combined average is not accepted.

## Focused Commands

```bash
python scripts/run_current_coverage_gates.py --bench bench15 --skip-e2e
python scripts/run_current_coverage_gates.py --bench bench16 --skip-e2e
python scripts/run_current_coverage_gates.py --bench bench15 --skip-python
python scripts/run_current_coverage_gates.py --bench bench16 --skip-python
```

## Current E2E Flow IDs

The current-flow manifest lives at `cypress/support/current_flows.json`.
Cypress specs mark a flow only after the user-visible assertion has passed:

```javascript
cy.markFlow("release.single-part-generates-bom");
```

Do not add IDs for removed behavior. When a feature is removed, delete the spec or remove the flow ID
from the manifest in the same change.

## Python Coverage Scope

Python coverage is recalculated from Frappe's `coverage.xml` for project-owned code. The checker
excludes tests, package markers, patches, generated/framework scaffolding, and pass-through DocType
controller files that contain no app behavior. If a previously empty file gains behavior, remove it
from the exclusion list and add behavior coverage.

Generated reports are written under `coverage-results/` and are not committed.
````

- [ ] **Step 2: Update `AGENTS.md` testing section**

Replace the paragraph that starts with `No test suite exists yet.` with:

````markdown
The app has Frappe-native Python tests and Cypress Desk tests. Add focused tests alongside the module
they exercise, using `test_*.py` filenames for Python and current-flow IDs for Cypress. Prefer tests
that verify document behavior, calculations, permissions, workflow, patches, and user-visible Desk
flows through Frappe APIs or the Desk UI. Before opening a PR, run the dual-bench coverage gate:

```bash
python scripts/run_current_coverage_gates.py
```

Each Python and Desk JS/E2E gate must be above 96% independently on bench15 and bench16.
````

- [ ] **Step 3: Commit**

```bash
git add docs/current-app-test-coverage.md AGENTS.md
git commit -m "docs: document current coverage gates"
```

## Task 7: Run And Triage The Full Gate

**Files:**
- Modify only current behavior tests if the report identifies a real uncovered current behavior.
- Do not add tests for removed `child_layout` or recursive behavior.
- Do not add schema-existence or schema-absence tests.

- [ ] **Step 1: Run the full gate**

Run:

```bash
python scripts/run_current_coverage_gates.py
```

Expected: four PASS lines:

```text
bench15 python PASS
bench15 e2e   PASS
bench16 python PASS
bench16 e2e   PASS
```

- [ ] **Step 2: If a Python gate is at or below 96%, inspect the report**

Run:

```bash
python - <<'PY'
import json
from pathlib import Path
for path in sorted(Path("coverage-results/python").glob("*-summary.json")):
    data = json.loads(path.read_text())
    print(path)
    for item in data["files"][:10]:
        missing = ", ".join(str(line) for line in item["missing"][:20])
        print(f"  {item['percent']}% {item['file']} missing {missing}")
PY
```

Add tests only for behavior represented by the missing lines. If the missing file is boilerplate with
no app behavior, update `PASS_THROUGH_DOCTYPES` in `scripts/check_python_coverage.py` instead of
writing a cosmetic test.

- [ ] **Step 3: If an E2E gate is at or below 96%, inspect missing flow IDs**

Run:

```bash
python scripts/check_e2e_flow_coverage.py \
  --report coverage-results/e2e/bench15-flow-coverage.json \
  --threshold 96 || true
python scripts/check_e2e_flow_coverage.py \
  --report coverage-results/e2e/bench16-flow-coverage.json \
  --threshold 96 || true
```

For each missing current-flow ID, either fix the existing current spec so the flow marks after its
assertions pass, or add a small Cypress assertion for that live behavior. If the flow ID describes
removed behavior, remove it from `cypress/support/current_flows.json`.

- [ ] **Step 4: Re-run after triage**

Run:

```bash
python scripts/run_current_coverage_gates.py
```

Expected: all four gates PASS.

- [ ] **Step 5: Final local checks**

Run:

```bash
node -c cypress.config.js
for file in cypress/integration/*.js cypress/support/e2e.js; do node -c "$file"; done
pre-commit run --all-files
```

Expected: all checks pass. If `pre-commit` is not on PATH, use the repo-local setup command from `docs/current-app-test-coverage.md` or report the missing tool.

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "test: enforce current app coverage gates"
```

## Self-Review

- Spec coverage: Tasks 1 and 4 remove stale removed-feature tests and cover only current flows. Tasks 2, 3, and 5 create the four independent gates. Task 6 documents commands and exclusions. Task 7 runs and triages the full gate.
- Placeholder scan: no placeholder markers or removed-feature coverage instructions remain.
- Type consistency: scripts use `bench15`, `bench16`, `development.localhost`, `frappe16.localhost`, `sheet_cutting_layout`, `coverage-results/python`, and `coverage-results/e2e` consistently.
