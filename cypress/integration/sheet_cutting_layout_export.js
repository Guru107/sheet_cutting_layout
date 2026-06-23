describe("Sheet Cutting Layout IATF export", () => {
	const suffix = Date.now();
	const layoutCode = `SCLEXP${suffix}`;
	const project = `SCLEXPPROJ${suffix}`;
	const rawMaterialItem = `SCLEXPRM${suffix}`;
	const processScrapItem = `SCLEXPSCRAP${suffix}`;
	const finishedPartItem = `EXPPART001${suffix}SHR`;
	let projectName;

	const downloadMethod =
		"sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout." +
		"sheet_cutting_layout.download_sheet_cutting_layout";

	function expectFormStatus(expectedStatus) {
		cy.window().should((win) => {
			expect(win.cur_frm.doc.status).to.equal(expectedStatus);
		});
	}

	before(() => {
		cy.login();
		cy.ensureHsnCode("720890");
		cy.call("frappe.client.insert", {
			doc: { doctype: "Project", name: project, project_name: project },
		}).then(({ message }) => {
			projectName = message.name;
		});
		[rawMaterialItem, processScrapItem, finishedPartItem].forEach((itemCode) => {
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

	it("downloads a non-empty .xlsx via the export endpoint", { retries: 0 }, () => {
		cy.call("frappe.client.insert", {
			doc: {
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
				finished_part_code: finishedPartItem,
				net_weight_per_part_kg: 15.52,
				gross_weight_per_part_kg: 15.72,
				scrap_weight_per_part_kg: 0.2,
			},
		}).then(({ message }) => {
			const layoutName = message.name;

			cy.visit(`/app/sheet-cutting-layout/${layoutName}`);
			expectFormStatus("Draft");
			cy.contains("button", "Download Layout (Excel)").should("exist");

			cy.request({
				method: "GET",
				url: `/api/method/${downloadMethod}?name=${encodeURIComponent(layoutName)}`,
				encoding: "binary",
			}).then((response) => {
				expect(response.status).to.equal(200);
				expect(response.headers["content-disposition"]).to.contain(".xlsx");
				expect(response.body.length).to.be.greaterThan(0);
				expect(response.body.slice(0, 2)).to.equal("PK");
				cy.markFlow("export.single-layout-downloads-xlsx");
			});
		});
	});
});
