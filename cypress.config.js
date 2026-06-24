const fs = require("fs");
const path = require("path");
const currentFlows = require("./cypress/support/current_flows.json");

function writeFlowReport(outputPath, covered, runId) {
	const coveredIds = [...covered].sort();
	const manifestIds = currentFlows.map((flow) => flow.id);
	const missing = manifestIds.filter((flowId) => !covered.has(flowId)).sort();

	fs.mkdirSync(path.dirname(outputPath), { recursive: true });
	fs.writeFileSync(
		outputPath,
		JSON.stringify(
			{
				runId,
				total: currentFlows.length,
				covered: coveredIds,
				missing,
			},
			null,
			2
		) + "\n"
	);
}

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
		setupNodeEvents(on) {
			const manifestIds = new Set(currentFlows.map((flow) => flow.id));
			const covered = new Set();
			const outputPath =
				process.env.SCL_FLOW_COVERAGE_OUTPUT ||
				path.join("cypress", "results", "current-flow-coverage.json");
			const runId = process.env.SCL_FLOW_COVERAGE_RUN_ID || Date.now().toString();

			writeFlowReport(outputPath, covered, runId);

			on("task", {
				markFlow(flowId) {
					if (!manifestIds.has(flowId)) {
						throw new Error(`Unknown current E2E flow ID: ${flowId}`);
					}
					covered.add(flowId);
					writeFlowReport(outputPath, covered, runId);
					return null;
				},
			});

			on("after:run", () => {
				writeFlowReport(outputPath, covered, runId);
			});
		},
	},
};
