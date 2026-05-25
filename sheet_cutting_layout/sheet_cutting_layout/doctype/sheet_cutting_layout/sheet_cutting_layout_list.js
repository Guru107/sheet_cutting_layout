frappe.listview_settings["Sheet Cutting Layout"] = {
	allow_edit: true,

	onload(listview) {
		listview.list_view_settings = listview.list_view_settings || {};
		listview.list_view_settings.allow_edit = true;
		listview.page.clear_actions_menu();
		listview.set_actions_menu_items();
	},
};
