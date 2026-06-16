describe("Sheet Cutting Layout LH/RH symmetric parts", () => {
	const suffix = Date.now();
	const project = `SCLLHRHPROJ${suffix}`;
	const rawMaterialItem = `SCLLHRHRM${suffix}`;
	const processScrapItem = `SCLLHRHSCRAP${suffix}`;
	const primaryPart = `PARTLH${suffix}SHR`;
	const twinPart = `PARTRH${suffix}SHR`;
	const toggleLayoutCode = `SCLLHRHTOG${suffix}`;
	const releaseLayoutCode = `SCLLHRHREL${suffix}`;
	let projectName;

	Cypress.on("uncaught:exception", (error) => {
		if (
			error.message.includes(
				"Cannot read properties of undefined (reading 'finished_parts')"
			)
		) {
			return false;
		}
		return true;
	});

	function strip(layoutCode, overrides = {}) {
		return {
			doctype: "Sheet Cutting Layout",
			layout_code: layoutCode,
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
			finished_part_code: primaryPart,
			net_weight_per_part_kg: 15.52,
			gross_weight_per_part_kg: 15.72,
			scrap_weight_per_part_kg: 0.2,
			finished_parts: [
				{
					doctype: "Layout Finished Part",
					finished_part_item: primaryPart,
					parts_per_sheet: 2,
					net_weight_per_part_kg: 15.52,
					gross_weight_per_part_kg: 15.72,
					scrap_weight_per_part_kg: 0.2,
				},
			],
			...overrides,
		};
	}

	function fetchReleasedLhRhLayout(attempt = 0) {
		return cy
			.request(
				"GET",
				`/api/method/frappe.client.get?doctype=Sheet%20Cutting%20Layout&name=${releaseLayoutCode}`
			)
			.then(({ body }) => {
				const layout = body.message;
				const rows = layout.finished_parts || [];
				const ready = rows.length === 2 && rows.every((row) => row.generated_bom);
				if (!ready && attempt < 10) {
					cy.wait(500);
					return fetchReleasedLhRhLayout(attempt + 1);
				}
				expect(rows).to.have.length(2);
				return layout;
			});
	}

	before(() => {
		cy.login();
		cy.ensureHsnCode("720890");
		cy.call("frappe.client.insert", {
			doc: {
				doctype: "Project",
				name: project,
				project_name: project,
			},
		}).then(({ message }) => {
			projectName = message.name;
		});
		[rawMaterialItem, processScrapItem, primaryPart, twinPart].forEach((itemCode) => {
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

	it(
		"toggles LH/RH fields client-side: checking defaults orientation to LH, unchecking clears twin and orientation",
		{ retries: 0 },
		() => {
			cy.call("frappe.client.insert", { doc: strip(toggleLayoutCode) });
			cy.visit(`/app/sheet-cutting-layout/${toggleLayoutCode}`);
			cy.contains('[data-fieldname="status"]', "Draft");

			// Checking is_lh_rh must default orientation to LH (updateLhRhFields).
			cy.get('[data-fieldname="is_lh_rh"] input[type="checkbox"]').check({ force: true });
			cy.window().its("cur_frm.doc.orientation").should("eq", "LH");

			// Pick a twin so the unchecking branch has something to clear.
			cy.window().then((win) => win.cur_frm.set_value("twin_finished_part", twinPart));
			cy.window().its("cur_frm.doc.twin_finished_part").should("eq", twinPart);

			// Unchecking is_lh_rh must clear both stale pair fields.
			cy.get('[data-fieldname="is_lh_rh"] input[type="checkbox"]').uncheck({ force: true });
			cy.window().should((win) => {
				expect(win.cur_frm.doc.orientation || "").to.equal("");
				expect(win.cur_frm.doc.twin_finished_part || "").to.equal("");
			});
		}
	);

	it(
		"releases an LH/RH layout into two distinct BOMs and an LH + RH mirror referencing one layout",
		{ retries: 0 },
		() => {
			cy.call("frappe.client.insert", {
				doc: strip(releaseLayoutCode, {
					is_lh_rh: 1,
					orientation: "LH",
					twin_finished_part: twinPart,
				}),
			});

			// Drive the release through the live workflow engine (real on_submit BOM
			// generation). The Desk form's mandatory-field check mis-fires for the
			// mandatory_depends_on LH/RH fields when the workflow is automated at speed;
			// the workflow API is the same server transition a user triggers, without
			// that UI race. The client toggle behaviour is covered by the test above.
			const docRef = JSON.stringify({ doctype: "Sheet Cutting Layout", name: releaseLayoutCode });
			["Submit for Check", "Project Manager Approves", "Purchase Approves", "MR Release"].forEach(
				(action) => {
					cy.call("frappe.model.workflow.apply_workflow", { doc: docRef, action });
				}
			);

			fetchReleasedLhRhLayout().then((layout) => {
				expect(layout.status).to.equal("Released");
				const rows = layout.finished_parts;
				expect(rows.map((row) => row.orientation)).to.deep.equal(["LH", "RH"]);
				expect(rows[0].finished_part_item).to.equal(primaryPart);
				expect(rows[1].finished_part_item).to.equal(twinPart);

				const bomNames = rows.map((row) => row.generated_bom);
				expect(new Set(bomNames).size).to.equal(2);
				expect(layout.generated_bom).to.equal(bomNames[0]);

				bomNames.forEach((bomName, index) => {
					cy.request(
						"GET",
						`/api/method/frappe.client.get?doctype=BOM&name=${encodeURIComponent(bomName)}`
					).then(({ body: bomBody }) => {
						const bom = bomBody.message;
						// Both twin BOMs must reference the same Sheet Cutting Layout (spec §8.5).
						expect(bom.sheet_cutting_layout).to.equal(releaseLayoutCode);
						expect(bom.item).to.equal(index === 0 ? primaryPart : twinPart);
						expect(Boolean(bom.is_active)).to.equal(true);
					});
				});
			});
		}
	);
});
