module.exports = {
	defaultCommandTimeout: 20000,
	pageLoadTimeout: 15000,
	video: true,
	viewportHeight: 960,
	viewportWidth: 1400,
	retries: {
		runMode: 1,
		openMode: 1,
	},
	env: {
		adminPassword: "123",
	},
	e2e: {
		baseUrl: "http://localhost:8002",
		specPattern: ["./cypress/integration/*.js"],
		testIsolation: true,
	},
};
