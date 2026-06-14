describe("Sheet Cutting Layout export + recursion arc", () => {
	const suffix = Date.now();
	const project = `SCLEXPPROJ${suffix}`;
	const rawMaterial = `SCLEXPRM${suffix}`;
	const scrapItem = `SCLEXPSCRAP${suffix}`;
	const childPart = `EXPCHILD${suffix}SHR`;
	const endPieceItem = `${childPart}-EP-2x500x1000`;
	const parentPart = `EXPPARENT${suffix}SHR`;
	const twinPart = `EXPTWIN${suffix}SHR`;
	const childCode = `SCLEXPCHILD${suffix}`;
	const parentCode = `SCLEXPPARENT${suffix}`;
	let projectName;

	const downloadMethod =
		"sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout." +
		"sheet_cutting_layout.download_sheet_cutting_layout";

	Cypress.on("uncaught:exception", () => false);

	function runWorkflowAction(action, expectedStatus) {
		cy.contains(".actions-btn-group button, button", "Actions").click();
		cy.contains(".dropdown-menu a, .dropdown-menu button", action).click();
		cy.get("body").then(($body) => {
			if ($body.find(".modal:visible").length) {
				cy.get(".modal:visible").within(() => {
					cy.contains("button", "Yes").click();
				});
			}
		});
		cy.get(".modal:visible").should("not.exist");
		cy.get(".freeze:visible").should("not.exist");
		if (expectedStatus) {
			cy.contains('[data-fieldname="status"]', expectedStatus);
		}
	}

	function releaseLayout(layoutCode) {
		cy.visit(`/app/sheet-cutting-layout/${layoutCode}`);
		runWorkflowAction("Submit for Check", "Submitted for Check");
		runWorkflowAction("Project Manager Approves", "PM Approved");
		runWorkflowAction("Purchase Approves", "Approved by Purchase");
		runWorkflowAction("MR Release", "Released");
		cy.contains('[data-fieldname="status"]', "Released");
	}

	function fetchLayout(layoutCode, attempt = 0) {
		return cy
			.request(
				"GET",
				`/api/method/frappe.client.get?doctype=Sheet%20Cutting%20Layout&name=${layoutCode}`
			)
			.then(({ body }) => {
				if (body.message.docstatus !== 2 && attempt < 10) {
					cy.wait(500);
					return fetchLayout(layoutCode, attempt + 1);
				}
				return body.message;
			});
	}

	function bomsForLayout(layoutCode) {
		return cy
			.request(
				"GET",
				`/api/method/frappe.client.get_list?doctype=BOM&filters=${encodeURIComponent(
					JSON.stringify([["sheet_cutting_layout", "=", layoutCode]])
				)}&fields=${encodeURIComponent(JSON.stringify(["name", "is_active", "docstatus"]))}`
			)
			.then(({ body }) => body.message);
	}

	before(() => {
		cy.login();
		cy.ensureHsnCode("720890");
		cy.call("frappe.client.insert", {
			doc: { doctype: "Project", name: project, project_name: project },
		});
		cy.call("frappe.client.get_value", {
			doctype: "Project",
			filters: { project_name: project },
			fieldname: "name",
		}).then(({ message }) => {
			projectName = message.name;
			[rawMaterial, scrapItem, endPieceItem].forEach((itemCode) => {
				cy.call("frappe.client.insert", {
					doc: {
						doctype: "Item",
						item_code: itemCode,
						item_name: itemCode,
						item_group: "All Item Groups",
						stock_uom: "Kg",
						is_stock_item: 1,
						valuation_rate: 50,
						gst_hsn_code: "720890",
					},
				});
			});
			[parentPart, twinPart, childPart].forEach((itemCode) => {
				cy.call("frappe.client.insert", {
					doc: {
						doctype: "Item",
						item_code: itemCode,
						item_name: itemCode,
						item_group: "All Item Groups",
						stock_uom: "Nos",
						is_stock_item: 1,
						valuation_rate: 50,
						gst_hsn_code: "720890",
					},
				});
			});
			cy.call("frappe.client.insert", {
				doc: {
					doctype: "Sheet Cutting Layout",
					layout_code: childCode,
					project: projectName,
					revision_no: 1,
					status: "Draft",
					raw_material_item: endPieceItem,
					process_scrap_item: scrapItem,
					sheet_thickness_mm: 2,
					sheet_width_mm: 500,
					sheet_length_mm: 1000,
					strip_thickness_mm: 2,
					strip_width_mm: 500,
					strip_length_mm: 1000,
					parts_per_strip: 1,
					no_of_strips: 1,
					finished_part_code: childPart,
					net_weight_per_part_kg: 7.86,
				},
			});
			cy.call("frappe.client.insert", {
				doc: {
					doctype: "Sheet Cutting Layout",
					layout_code: parentCode,
					project: projectName,
					revision_no: 1,
					status: "Draft",
					raw_material_item: rawMaterial,
					process_scrap_item: scrapItem,
					sheet_thickness_mm: 2,
					sheet_width_mm: 1000,
					sheet_length_mm: 1000,
					strip_thickness_mm: 2,
					strip_width_mm: 500,
					strip_length_mm: 1000,
					parts_per_strip: 1,
					no_of_strips: 1,
					finished_part_code: parentPart,
					is_lh_rh: 1,
					orientation: "LH",
					twin_finished_part: twinPart,
					net_weight_per_part_kg: 7.86,
					end_pieces: [
						{
							doctype: "Layout End Piece",
							width_mm: 500,
							length_mm: 1000,
							disposition: "Reuse",
							used_for_finished_part: childPart,
							scrap_item: scrapItem,
							child_layout: childCode,
							bom_quantity: 1,
							net_weight_per_part_kg: 7.86,
						},
					],
				},
			});
		});
	});

	beforeEach(() => {
		cy.login();
	});

	it("releases, downloads, supersedes, and cascades retirement", { retries: 0 }, () => {
		releaseLayout(childCode);
		releaseLayout(parentCode);

		cy.request({
			method: "GET",
			url: `/api/method/${downloadMethod}?name=${encodeURIComponent(parentCode)}`,
			encoding: "binary",
		}).then((response) => {
			expect(response.status).to.equal(200);
			expect(response.headers["content-disposition"]).to.contain(".xlsx");
			expect(response.body.length).to.be.greaterThan(1000);
			expect(response.body.slice(0, 2)).to.equal("PK");
		});

		cy.visit(`/app/sheet-cutting-layout/${parentCode}`);
		runWorkflowAction("Supersede");
		cy.get(".freeze:visible").should("not.exist");

		fetchLayout(parentCode).then((parent) => {
			expect(parent.docstatus).to.equal(2);
		});
		fetchLayout(childCode).then((child) => {
			expect(child.docstatus).to.equal(2);
		});
		[parentCode, childCode].forEach((layoutCode) => {
			bomsForLayout(layoutCode).then((boms) => {
				expect(boms).to.not.be.empty;
				boms.forEach((bom) => {
					expect(Boolean(bom.is_active)).to.equal(false);
				});
			});
		});
	});
});
