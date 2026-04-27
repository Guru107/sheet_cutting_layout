describe("Sheet Cutting Layout release workflow", () => {
	const suffix = Date.now();
	const layoutCode = `SCLCY${suffix}`;
	const layoutFamily = `SCLFAMCY${suffix}`;
	const rawMaterialItem = `SCLRMCY${suffix}`;
	const processScrapItem = `SCLSCRAPCY${suffix}`;
	const lhItem = `PART001LH${suffix}SHR`;
	const rhItem = `PART001RH${suffix}SHR`;

	function setField(fieldname, value) {
		cy.get(`[data-fieldname="${fieldname}"]`).find("input, textarea").first().clear().type(`${value}`);
	}

	function addFinishedPart(itemCode, grossWeightKg) {
		cy.get('[data-fieldname="finished_parts"]').contains("button", "Add Row").click();
		cy.get('[data-fieldname="finished_parts"] .grid-row').last().as("row");
		cy.get("@row").find('[data-fieldname="finished_part_item"] input').clear().type(`${itemCode}{enter}`);
		cy.get("@row").find('[data-fieldname="parts_per_sheet"] input').clear().type("1");
		cy.get("@row")
			.find('[data-fieldname="gross_weight_per_part_kg"] input')
			.clear()
			.type(`${grossWeightKg}`);
		cy.get("@row").find('[data-fieldname="scrap_weight_per_part_kg"] input').clear().type("0.2");
	}

	function runWorkflowAction(action) {
		cy.contains(".actions-btn-group button, button", "Actions").click();
		cy.contains(".dropdown-menu a, .dropdown-menu button", action).click();
		cy.get(".modal:visible").within(() => {
			cy.contains("button", "Yes").click();
		});
		cy.get(".modal:visible").should("not.exist");
		cy.get(".freeze:visible").should("not.exist");
	}

	before(() => {
		cy.login();
		[rawMaterialItem, processScrapItem, lhItem, rhItem].forEach((itemCode) => {
			cy.call("frappe.client.insert", {
				doc: {
					doctype: "Item",
					item_code: itemCode,
					item_name: itemCode,
					item_group: "All Item Groups",
					stock_uom: "Kg",
					is_stock_item: 1,
				},
			});
		});
	});

	it("releases LH/RH finished parts and shows generated BOM links", () => {
		cy.visit("/app/sheet-cutting-layout/new-sheet-cutting-layout-1");

		setField("layout_code", layoutCode);
		setField("layout_family", layoutFamily);
		setField("revision_no", 1);
		setField("raw_material_item", `${rawMaterialItem}{enter}`);
		setField("process_scrap_item", `${processScrapItem}{enter}`);
		setField("sheet_thickness_mm", 2);
		setField("sheet_width_mm", 1000);
		setField("sheet_length_mm", 2000);
		setField("weight_per_sheet_kg", 20);
		setField("strip_thickness_mm", 2);
		setField("strip_width_mm", 100);
		setField("strip_length_mm", 2000);
		setField("weight_of_strip_kg", 2);
		setField("parts_per_strip", 1);
		setField("no_of_strips", 2);
		setField("parts_per_sheet", 2);

		addFinishedPart(lhItem, 2.5);
		addFinishedPart(rhItem, 2.5);

		cy.contains("button", "Save").click();
		cy.contains('[data-fieldname="status"]', "Draft");

		runWorkflowAction("Submit for Check");
		runWorkflowAction("Project Manager Approves");
		runWorkflowAction("Manufacturing Manager Approves");
		runWorkflowAction("Mark Checked");
		runWorkflowAction("Purchase Approves");
		runWorkflowAction("MR Release");

		cy.contains('[data-fieldname="status"]', "Released");
		cy.get('[data-fieldname="finished_parts"] .grid-row')
			.should("have.length", 2)
			.each(($row, index) => {
				const expectedItem = index === 0 ? lhItem : rhItem;
				cy.wrap($row)
					.find('[data-fieldname="generated_bom"] input')
					.invoke("val")
					.then((bomName) => {
						expect(bomName).to.be.a("string").and.not.be.empty;
						cy.call("frappe.client.get", {
							doctype: "BOM",
							name: bomName,
						}).then(({ message }) => {
							expect(message.name).to.equal(bomName);
							expect(message.item).to.equal(expectedItem);
							expect(Boolean(message.is_active)).to.equal(true);
						});
					});
			});
	});
});
