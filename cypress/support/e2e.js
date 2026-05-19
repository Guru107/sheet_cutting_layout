Cypress.Commands.add("login", () => {
	cy.request({
		method: "POST",
		url: "/api/method/login",
		body: {
			usr: "Administrator",
			pwd: Cypress.env("adminPassword"),
		},
	});
});

Cypress.Commands.add("call", (method, args = {}) => {
	return cy.request({
		method: "POST",
		url: `/api/method/${method}`,
		body: args,
	}).then((res) => {
		expect(res.status).to.equal(200);
		return res.body;
	});
});

Cypress.Commands.add("ensureHsnCode", (hsnCode) => {
	return cy
		.call("frappe.client.get_value", {
			doctype: "GST HSN Code",
			filters: { hsn_code: hsnCode },
			fieldname: "name",
		})
		.then(({ message }) => {
			if (message?.name) {
				return;
			}

			return cy.call("frappe.client.insert", {
				doc: {
					doctype: "GST HSN Code",
					hsn_code: hsnCode,
					description: "Cypress test HSN code",
				},
			});
		});
});
