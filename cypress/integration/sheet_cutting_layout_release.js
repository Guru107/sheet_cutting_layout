describe("Sheet Cutting Layout release workflow", () => {
	const suffix = Date.now();
	const layoutCode = `SCLCY${suffix}`;
	const project = `SCLPROJCY${suffix}`;
	const rawMaterialItem = `SCLRMCY${suffix}`;
	const processScrapItem = `SCLSCRAPCY${suffix}`;
	const finishedPartItem = `PART001${suffix}SHR`;
	let projectName;

	Cypress.on("uncaught:exception", (error) => {
		if (error.message.includes("Cannot read properties of undefined (reading 'finished_parts')")) {
			return false;
		}
		return true;
	});

	function setField(fieldname, value) {
		cy.get(`[data-fieldname="${fieldname}"]`).find("input, textarea").first().clear().type(`${value}`);
	}

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

	function fetchReleasedLayoutWithBom(attempt = 0) {
		return cy
			.request(
				"GET",
				`/api/method/frappe.client.get?doctype=Sheet%20Cutting%20Layout&name=${layoutCode}`
			)
			.then(({ body }) => {
				const layout = body.message;
				const bomName = layout.finished_parts?.[0]?.generated_bom;
				if (!bomName && attempt < 10) {
					cy.wait(500);
					return fetchReleasedLayoutWithBom(attempt + 1);
				}
				expect(layout.finished_parts).to.have.length(1);
				expect(bomName).to.be.a("string").and.not.be.empty;
				return { layout, bomName };
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

	it("releases one finished part, creates a Shearing BOM, and allows a new version", { retries: 0 }, () => {
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
		cy.visit(`/app/sheet-cutting-layout/${layoutCode}`);
		cy.contains('[data-fieldname="status"]', "Draft");

		runWorkflowAction("Submit for Check", "Submitted for Check");
		runWorkflowAction("Projects Manager Approves", "Submitted for Check");
		runWorkflowAction("Manufacturing Manager Approves", "Checked");
		runWorkflowAction("Purchase Approves", "Approved by Purchase");
		runWorkflowAction("MR Release", "Released");

		cy.contains('[data-fieldname="status"]', "Released");
		fetchReleasedLayoutWithBom().then(({ bomName }) => {
			cy.request("GET", `/api/method/frappe.client.get?doctype=BOM&name=${bomName}`).then(({ body: bomBody }) => {
				const message = bomBody.message;
				expect(message.name).to.equal(bomName);
				expect(message.item).to.equal(finishedPartItem);
				expect(message.quantity).to.equal(2);
				expect(message.custom_operation).to.equal("Shearing");
				expect(message.sheet_cutting_layout).to.equal(layoutCode);
				expect(Boolean(message.is_active)).to.equal(true);
				expect(message.items[0].item_code).to.equal(rawMaterialItem);
				expect(Number(message.items[0].qty)).to.be.closeTo(31.44, 0.001);
			});
		});
		cy.contains("button", "New Version").click();
		cy.contains('[data-fieldname="status"]', "Draft");
		cy.get('[data-fieldname="project"] input').should("have.value", project);
		cy.get('[data-fieldname="revision_no"] input').should("have.value", "2");
	});
});
