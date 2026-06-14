describe("Sheet Cutting Layout consumption tracking", () => {
	const suffix = Date.now();
	const layoutCode = `SCLCONS${suffix}`;
	const project = `SCLCONSPROJ${suffix}`;
	const rawMaterialItem = `SCLCONSRM${suffix}`;
	const processScrapItem = `SCLCONSSCRAP${suffix}`;
	const finishedPartItem = `SCLCONSPART${suffix}SHR`;
	const endPieceItem = `SCLCONSEP${suffix}`;
	let projectName;

	function setField(fieldname, value) {
		cy.get(`[data-fieldname="${fieldname}"]`)
			.find("input, textarea")
			.first()
			.clear({ force: true })
			.type(`${value}`, { force: true });
		cy.get("body").type("{esc}", { force: true });
	}

	function readFieldValue(fieldname) {
		return cy
			.get(`[data-fieldname="${fieldname}"]`)
			.find("input, textarea, .control-value")
			.first()
			.then(($field) => $field.val() || $field.text());
	}

	function expectFieldNumber(fieldname, expectedValue, tolerance = 0.001) {
		readFieldValue(fieldname).then((value) => {
			expect(Number(value)).to.be.closeTo(expectedValue, tolerance);
		});
	}

	function expectFieldValue(fieldname, expectedValue) {
		cy.get(`[data-fieldname="${fieldname}"]`)
			.find("input, textarea, .control-value")
			.first()
			.then(($field) => {
				expect($field.val() || $field.text()).to.equal(expectedValue);
			});
	}

	function setDocField(fieldname, value) {
		cy.window().then((win) =>
			win.frappe.model.set_value(win.cur_frm.doctype, win.cur_frm.docname, fieldname, value)
		);
	}

	function addEndPiece() {
		cy.window().then((win) => {
			const frm = win.cur_frm;
			const row = win.frappe.model.add_child(frm.doc, "Layout End Piece", "end_pieces");
			return win.frappe.run_serially([
				() => win.frappe.model.set_value(row.doctype, row.name, "width_mm", 1250),
				() => win.frappe.model.set_value(row.doctype, row.name, "length_mm", 179),
				() => win.frappe.model.set_value(row.doctype, row.name, "disposition", "Scrap"),
				() =>
					win.frappe.model.set_value(row.doctype, row.name, "scrap_item", endPieceItem),
				() => frm.refresh_field("end_pieces"),
			]);
		});
	}

	function recalculateLayoutFields() {
		cy.window().then((win) => {
			const frm = win.cur_frm;
			return win.frappe.run_serially([
				() => frm.script_manager.trigger("sheet_length_mm"),
				() => frm.script_manager.trigger("strip_length_mm"),
				() => frm.script_manager.trigger("parts_per_strip"),
				() => frm.script_manager.trigger("no_of_strips"),
			]);
		});
	}

	before(() => {
		cy.login();
		cy.ensureHsnCode("720890");
		cy.call("frappe.client.insert", {
			doc: {
				doctype: "Project",
				project_name: project,
			},
		}).then(({ message }) => {
			projectName = message.name;
		});
		[rawMaterialItem, processScrapItem, finishedPartItem, endPieceItem].forEach((itemCode) => {
			cy.call("frappe.client.insert", {
				doc: {
					doctype: "Item",
					item_code: itemCode,
					item_name: itemCode,
					item_group: "All Item Groups",
					stock_uom: "Kg",
					is_stock_item: 1,
					gst_hsn_code: "720890",
				},
			});
		});
	});

	beforeEach(() => {
		cy.login();
	});

	it("shows balanced consumption for the customer-provided 1250 x 2500 x 1.6 layout", () => {
		cy.visit("/app/sheet-cutting-layout/new-sheet-cutting-layout-1");

		setField("layout_code", layoutCode);
		setDocField("project", projectName);
		setField("revision_no", 1);
		setDocField("raw_material_item", rawMaterialItem);
		setDocField("process_scrap_item", processScrapItem);
		setField("sheet_width_mm", 1250);
		setField("sheet_length_mm", 2500);
		setField("sheet_thickness_mm", 1.6);
		setField("strip_width_mm", 1250);
		setField("strip_length_mm", 211);
		setField("strip_thickness_mm", 1.6);
		setField("no_of_strips", 11);
		setField("parts_per_strip", 7);
		setDocField("finished_part_code", finishedPartItem);
		setField("net_weight_per_part_kg", 0.288846);
		recalculateLayoutFields();

		addEndPiece();

		expectFieldNumber("weight_per_sheet_kg", 39.3, 0.5);
		expectFieldNumber("weight_of_strip_kg", 3.31692, 0.01);
		expectFieldNumber("consumed_weight_kg", 39.3, 0.5);
		expectFieldNumber("leftover_weight_kg", 0);
		expectFieldValue("consumption_status", "Balanced");

		cy.intercept("POST", "/api/method/frappe.desk.form.save.savedocs").as("saveLayout");
		cy.window().then((win) => {
			win.cur_frm.save();
		});
		cy.wait("@saveLayout", { timeout: 30000 }).its("response.statusCode").should("eq", 200);
		cy.get(".freeze:visible").should("not.exist");
		cy.contains('[data-fieldname="status"]', "Draft");
	});
});
