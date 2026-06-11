from __future__ import annotations

try:
	import frappe
except ImportError:
	frappe = None


LEGACY_ROLE = "Projects Manager"
NEW_ROLE = "Project Manager"


def execute() -> None:
	if not frappe:
		raise RuntimeError("Frappe is required to migrate Sheet Cutting Layout approver roles")

	if not frappe.db.exists("Role", LEGACY_ROLE):
		return

	_ensure_role(NEW_ROLE)

	legacy_users = frappe.db.get_all(
		"Has Role",
		filters={"role": LEGACY_ROLE, "parenttype": "User"},
		pluck="parent",
	)
	for user in sorted(set(legacy_users)):
		if not frappe.db.exists("User", user):
			continue
		if frappe.db.exists("Has Role", {"role": NEW_ROLE, "parent": user, "parenttype": "User"}):
			continue
		user_doc = frappe.get_doc("User", user)
		user_doc.append("roles", {"role": NEW_ROLE})
		user_doc.save(ignore_permissions=True)


def _ensure_role(role_name: str) -> None:
	if frappe.db.exists("Role", role_name):
		return
	role = frappe.new_doc("Role")
	role.role_name = role_name
	role.desk_access = 1
	role.is_custom = 1
	role.insert(ignore_permissions=True)
