# Reject Returns Layout To Draft Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rejecting a Sheet Cutting Layout sends it back to `Draft` so the creator can correct and resubmit it, while preserving rejection audit history.

**Architecture:** Keep the workflow simple: change `Reject` transitions to target `Draft`. Preserve the audit table by recording a rejection snapshot when status changes from an approval state back to `Draft`. Do not reintroduce workflow wrapper hooks or add a new state.

**Tech Stack:** Frappe Workflow fixtures, Python DocType controller hooks, bench-native Frappe tests.

---

## File Structure

- Modify `sheet_cutting_layout/fixtures/workflow.json`: point existing `Reject` transitions to `Draft`.
- Modify `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`: infer rejection snapshot from approval-state to Draft transition.
- Modify `sheet_cutting_layout/tests/test_sheet_cutting_layout_controller.py`: update workflow integration test to expect Draft and add coverage for edit/resubmit path.
- Modify `sheet_cutting_layout/tests/test_release_service.py`: add a fixture contract test that all Reject transitions return to Draft.

---

### Task 1: Reject Workflow Returns To Draft

**Files:**
- Modify: `sheet_cutting_layout/fixtures/workflow.json`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
- Modify: `sheet_cutting_layout/tests/test_sheet_cutting_layout_controller.py`
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Add the failing workflow fixture contract test**

In `sheet_cutting_layout/tests/test_release_service.py`, add this method to `TestReleaseContracts` after `test_status_options_use_superseded_as_cancel_state`:

```python
def test_reject_workflow_transitions_return_to_draft(self) -> None:
	workflow_path = Path(__file__).resolve().parents[1] / "fixtures" / "workflow.json"
	workflow = json.loads(workflow_path.read_text(encoding="utf-8"))[0]
	reject_transitions = [
		transition
		for transition in workflow["transitions"]
		if transition["action"] == "Reject"
	]

	self.assertEqual(
		{
			transition["state"]: transition["next_state"]
			for transition in reject_transitions
		},
		{
			"Submitted for Check": "Draft",
			"PM Approved": "Draft",
			"Approved by Purchase": "Draft",
		},
	)
```

- [ ] **Step 2: Run the fixture contract test and verify it fails**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected: FAIL because the three `Reject` transitions still have `next_state: "Rejected"`.

- [ ] **Step 3: Change Reject transitions to Draft in the workflow fixture**

In `sheet_cutting_layout/fixtures/workflow.json`, change each of the three `Reject` transitions from:

```json
"next_state": "Rejected"
```

to:

```json
"next_state": "Draft"
```

Only change the transitions whose `"action"` is `"Reject"`. Leave the existing `Rejected` workflow state in the fixture for compatibility with existing records and status options.

- [ ] **Step 4: Add the failing controller workflow behavior test**

In `sheet_cutting_layout/tests/test_sheet_cutting_layout_controller.py`, replace `test_draft_workflow_actions_persist_approval_snapshots_after_reload` with:

```python
def test_reject_returns_layout_to_draft_and_records_snapshot(self) -> None:
	from frappe.model.workflow import apply_workflow

	layout = make_layout(
		finished_part_code=f"SCLTESTFG{frappe.generate_hash(length=5).upper()}SHR",
		parts_per_strip=1,
		no_of_strips=1,
		strip_length_mm=2500,
	).insert()

	layout = apply_workflow(layout, "Submit for Check")
	layout = apply_workflow(layout, "Reject")
	layout.reload()

	self.assertEqual(layout.status, "Draft")
	self.assertEqual(layout.docstatus, 0)
	layout.notes = "Corrected after rejection"
	layout.save()
	layout = apply_workflow(layout, "Submit for Check")
	layout.reload()

	self.assertEqual(layout.status, "Submitted for Check")
	snapshots = [(row.step_name, row.decision) for row in layout.approval_snapshot]
	self.assertEqual(
		snapshots,
		[
			("Submit for Check", "Submitted"),
			("Rejection", "Rejected"),
		],
	)
```

This verifies the selected user behavior without adding another workflow state.

- [ ] **Step 5: Run the controller test and verify the snapshot assertion fails**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_sheet_cutting_layout_controller
```

Expected: FAIL because rejection now returns to `Draft`, but `_record_draft_workflow_snapshot()` does not yet record a `Reject` snapshot for approval-state to Draft transitions.

- [ ] **Step 6: Record rejection snapshot for approval-state to Draft transitions**

In `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`, add this constant below `_DRAFT_STATUS_SNAPSHOT_ACTIONS`:

```python
_REJECTABLE_STATUSES = frozenset(
	{
		"Submitted for Check",
		"PM Approved",
		"Approved by Purchase",
	}
)
```

Then replace `_record_draft_workflow_snapshot()` with:

```python
def _record_draft_workflow_snapshot(doc: object) -> None:
	status = getattr(doc, "status", None)
	previous_status = _previous_status(doc)
	action = _draft_workflow_snapshot_action(status=status, previous_status=previous_status)
	if not action:
		return

	row = approval_snapshot_row(
		action=action,
		approver=_get_session_user(),
		decision_time=_get_now_datetime(),
	)
	if row is None or _has_approval_snapshot(doc, step_name=str(row["step_name"])):
		return

	_insert_approval_snapshot_row(doc, row=row)
```

Add this helper immediately below `_record_draft_workflow_snapshot()`:

```python
def _draft_workflow_snapshot_action(*, status: object, previous_status: object) -> str | None:
	if previous_status in {None, status}:
		return None
	if status == "Draft" and previous_status in _REJECTABLE_STATUSES:
		return REJECT_ACTION
	return _DRAFT_STATUS_SNAPSHOT_ACTIONS.get(status)
```

Do not add `before_workflow_action`, `after_workflow_action`, or a server-side workflow wrapper.

- [ ] **Step 7: Run focused tests**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_sheet_cutting_layout_controller
```

Expected: both modules pass.

- [ ] **Step 8: Migrate workflow fixture into the bench site**

Run:

```bash
bench --site development.localhost migrate
```

Expected: migration completes and fixture updates apply.

- [ ] **Step 9: Run final verification**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout
pre-commit run --all-files
```

Expected: full app tests and pre-commit pass.

- [ ] **Step 10: Commit implementation**

Run:

```bash
git add sheet_cutting_layout/fixtures/workflow.json sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py sheet_cutting_layout/tests/test_sheet_cutting_layout_controller.py sheet_cutting_layout/tests/test_release_service.py
git commit -m "fix: return rejected layouts to draft"
```

