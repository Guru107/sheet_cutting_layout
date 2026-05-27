# Development Philosophy

- Test-driven development is the only development path in this repository.
- Always use bench native and frappe native testing frameworks.
- The coverage must always be above 96%.
- When implementing any feature or a behaviour always adhere to frappe, erpnext coding standards.
- Always check if a particular feature or behaviour is already handled by frappe or erpnext then use the same where possible, follow DRY principles when coding.
- Always look to have mimimum customizations, if there is a way to solve a particular problem without customization then give the option to choose if we want to go with already existing behaviour or implement new feature.
- Always stay close to frappe and erpnext framework.

No production behavior should be added or changed without first writing a failing test that describes
the required behavior. The cycle is always:

1. Write the smallest meaningful failing test.
2. Run it and confirm it fails for the expected reason.
3. Implement the smallest change that makes it pass.
4. Refactor only while the test suite stays green.

## Required Test Coverage Shape

Use the lightest test that proves the behavior, then add broader tests where risk justifies it.

- Unit tests: pure calculations, validators, naming helpers, and small services.
- Integration tests: DocType controllers, hooks, permissions, database behavior, and patches.
- End-to-end tests: critical user workflows in the Frappe Desk or website.
- Property-based tests: layout, nesting, optimization, and geometry invariants.
- Model-based tests: stateful flows where many operation sequences must preserve business rules.

## Frappe Test Commands

Run Python tests from the bench root:

```bash
bench --site <site-name> run-tests --app sheet_cutting_layout
```

Use Cypress for end-to-end tests because it is supported by Frappe bench. Place UI specs under
`cypress/integration` and run them from the bench root:

```bash
bench --site <site-name> run-ui-tests sheet_cutting_layout
bench --site <site-name> run-ui-tests sheet_cutting_layout --headless
```

## Review Standard

Pull requests without tests are incomplete unless they only change documentation. Test gaps must be
called out explicitly with the reason and the follow-up plan.
