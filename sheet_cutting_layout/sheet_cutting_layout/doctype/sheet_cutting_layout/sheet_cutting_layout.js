frappe.provide("sheet_cutting_layout");

(() => {
	"use strict";

	const SHEET_LAYOUT_CANVAS_ASSET = "/assets/sheet_cutting_layout/js/sheet_layout_canvas.js";
	const SHEET_LAYOUT_PREVIEW_ID = "sheet-layout-canvas-preview";
	const SHEET_LAYOUT_REDRAW_MS = 200;
	const STEEL_DENSITY_G_PER_CM3 = 7.86;
	const DEFAULT_FLOAT_PRECISION = 6;
	const SHEET_CONSUMPTION_PRECISION = 3;
	const SHEET_CONSUMPTION_TOLERANCE_KG = 0.005;

	const SHEET_LAYOUT_FIELDS = [
		"sheet_thickness_mm",
		"sheet_width_mm",
		"sheet_length_mm",
		"strip_thickness_mm",
		"strip_width_mm",
		"strip_length_mm",
		"parts_per_strip",
		"no_of_strips",
		"parts_per_sheet",
		"weight_per_sheet_kg",
		"weight_of_strip_kg",
		"consumed_weight_kg",
		"leftover_weight_kg",
		"consumption_status",
	];

	const APPROVAL_SNAPSHOT_ACTIONS = {
		"Projects Manager Approves": "Projects Manager Approval",
		"Manufacturing Manager Approves": "Manufacturing Manager Approval",
		"Purchase Approves": "Purchase Approval",
		Reject: "Rejection",
	};

	function loadSheetLayoutCanvas() {
		if (window.SheetLayoutCanvas) {
			return Promise.resolve();
		}

		return new Promise((resolve) => {
			frappe.require(SHEET_LAYOUT_CANVAS_ASSET, resolve);
		});
	}

	function ensurePreviewCanvas(frm) {
		if (frm.sheet_layout_canvas) {
			return frm.sheet_layout_canvas;
		}

		const wrapper = document.createElement("div");
		wrapper.id = SHEET_LAYOUT_PREVIEW_ID;
		wrapper.className = "sheet-layout-canvas-preview";
		wrapper.style.margin = "16px 0";
		wrapper.style.padding = "12px";
		wrapper.style.border = "1px solid var(--border-color, #d1d8dd)";
		wrapper.style.background = "var(--fg-color, #ffffff)";

		const canvas = document.createElement("canvas");
		canvas.style.display = "block";
		canvas.style.width = "100%";
		canvas.style.height = "420px";
		canvas.style.minHeight = "320px";
		canvas.setAttribute("aria-label", __("Sheet cutting layout preview"));
		wrapper.appendChild(canvas);

		const anchor = frm.fields_dict.finished_parts?.wrapper || frm.layout?.wrapper;
		if (anchor && anchor.parentNode) {
			anchor.parentNode.insertBefore(wrapper, anchor);
		} else {
			frm.wrapper.find(".form-layout").first().prepend(wrapper);
		}

		frm.sheet_layout_canvas = canvas;
		return canvas;
	}

	function redrawSheetLayout(frm) {
		loadSheetLayoutCanvas().then(() => {
			const canvas = ensurePreviewCanvas(frm);
			const payload = window.SheetLayoutCanvas.buildPayloadFromDoc(frm.doc || {});
			window.SheetLayoutCanvas.render(canvas, payload);
		});
	}

	function scheduleSheetLayoutRedraw(frm) {
		if (!frm.sheet_layout_redraw) {
			frm.sheet_layout_redraw = window.SheetLayoutCanvas
				? window.SheetLayoutCanvas.debounce(
						() => redrawSheetLayout(frm),
						SHEET_LAYOUT_REDRAW_MS
				  )
				: frappe.utils.debounce(() => redrawSheetLayout(frm), SHEET_LAYOUT_REDRAW_MS);
		}
		frm.sheet_layout_redraw();
	}

	function scheduleParentRedraw(frm) {
		scheduleSheetLayoutRedraw(frm);
	}

	function calculateSheetWeight(frm) {
		return calculateWeight(
			frm.doc.sheet_thickness_mm,
			frm.doc.sheet_width_mm,
			frm.doc.sheet_length_mm
		);
	}

	function calculateStripWeight(frm) {
		return calculateWeight(
			frm.doc.strip_thickness_mm,
			frm.doc.strip_width_mm,
			frm.doc.strip_length_mm
		);
	}

	function calculateWeight(thicknessValue, widthValue, lengthValue) {
		const thickness = Number(thicknessValue);
		const width = Number(widthValue);
		const length = Number(lengthValue);
		if (!(thickness > 0 && width > 0 && length > 0)) {
			return null;
		}

		return Number(
			((length * width * thickness * getSteelDensity()) / 1000000).toFixed(
				getCalculationPrecision()
			)
		);
	}

	function getFloatPrecision() {
		return cint(frappe.boot.sysdefaults.float_precision) || 6;
	}

	function getCalculationPrecision() {
		return Math.max(getFloatPrecision(), DEFAULT_FLOAT_PRECISION);
	}

	function getSteelDensity() {
		return Number(STEEL_DENSITY_G_PER_CM3.toFixed(getFloatPrecision()));
	}

	function updateSheetWeight(frm) {
		const weight = calculateSheetWeight(frm);
		if (weight === null || frm.doc.weight_per_sheet_kg === weight) {
			return Promise.resolve();
		}

		return frm.set_value("weight_per_sheet_kg", weight);
	}

	function updateStripWeight(frm) {
		const weight = calculateStripWeight(frm);
		if (weight === null || frm.doc.weight_of_strip_kg === weight) {
			return Promise.resolve();
		}

		return frm.set_value("weight_of_strip_kg", weight);
	}

	function calculateGrossWeightPerPart(frm) {
		const stripWeight = Number(frm.doc.weight_of_strip_kg);
		const partsPerStrip = Number(frm.doc.parts_per_strip);
		if (!(stripWeight >= 0 && partsPerStrip > 0)) {
			return null;
		}

		return Number((stripWeight / partsPerStrip).toFixed(getCalculationPrecision()));
	}

	function calculatePartsPerSheet(frm) {
		const partsPerStrip = Number(frm.doc.parts_per_strip);
		const noOfStrips = Number(frm.doc.no_of_strips);
		if (!(partsPerStrip > 0 && noOfStrips > 0)) {
			return null;
		}

		return cint(partsPerStrip) * cint(noOfStrips);
	}

	function calculateEndPieceWeight(frm, row) {
		return calculateWeight(frm.doc.sheet_thickness_mm, row.width_mm, row.length_mm);
	}

	function updateFinishedPartWeights(frm) {
		const grossWeight = calculateGrossWeightPerPart(frm);
		if (grossWeight === null) {
			return Promise.resolve();
		}

		const updates = (frm.doc.finished_parts || []).flatMap((row) => {
			if (!row.finished_part_item) {
				return [];
			}
			const scrapWeight = Number(
				(grossWeight - numberOrZero(row.net_weight_per_part_kg)).toFixed(
					getCalculationPrecision()
				)
			);
			const rowUpdates = [];
			if (row.gross_weight_per_part_kg !== grossWeight) {
				rowUpdates.push(
					frappe.model.set_value(
						row.doctype,
						row.name,
						"gross_weight_per_part_kg",
						grossWeight
					)
				);
			}
			if (row.scrap_weight_per_part_kg !== scrapWeight) {
				rowUpdates.push(
					frappe.model.set_value(
						row.doctype,
						row.name,
						"scrap_weight_per_part_kg",
						scrapWeight
					)
				);
			}
			return rowUpdates;
		});

		return Promise.all(updates);
	}

	function updatePartsPerSheet(frm) {
		const partsPerSheet = calculatePartsPerSheet(frm);
		if (partsPerSheet === null) {
			return Promise.resolve();
		}

		const updates = [];
		if (frm.doc.parts_per_sheet !== partsPerSheet) {
			updates.push(frm.set_value("parts_per_sheet", partsPerSheet));
		}
		(frm.doc.finished_parts || []).forEach((row) => {
			if (!row.finished_part_item) {
				return;
			}
			if (row.parts_per_sheet !== partsPerSheet) {
				updates.push(
					frappe.model.set_value(row.doctype, row.name, "parts_per_sheet", partsPerSheet)
				);
			}
		});

		return Promise.all(updates);
	}

	function updateEndPieceWeights(frm) {
		const updates = (frm.doc.end_pieces || []).flatMap((row) => {
			const weight = calculateEndPieceWeight(frm, row);
			if (weight === null || row.weight_kg === weight) {
				return [];
			}
			return [frappe.model.set_value(row.doctype, row.name, "weight_kg", weight)];
		});

		return Promise.all(updates);
	}

	function calculateConsumptionTracking(frm) {
		const finishedParts = frm.doc.finished_parts || [];
		const endPieces = frm.doc.end_pieces || [];
		const consumedWeight = roundConsumptionWeight(
			finishedParts.reduce((total, row) => {
				if (!row.finished_part_item) {
					return total;
				}
				return (
					total +
					numberOrZero(row.gross_weight_per_part_kg) * numberOrZero(row.parts_per_sheet)
				);
			}, 0) +
				endPieces.reduce(
					(total, row) =>
						total + numberOrZero(row.weight_kg) * numberOrZero(row.qty_per_sheet),
					0
				)
		);
		const leftoverWeight = roundConsumptionWeight(
			roundConsumptionWeight(frm.doc.weight_per_sheet_kg) - consumedWeight
		);

		return {
			consumed_weight_kg: consumedWeight,
			leftover_weight_kg: leftoverWeight,
			consumption_status: getConsumptionStatus(leftoverWeight),
		};
	}

	function updateConsumptionTracking(frm) {
		const values = calculateConsumptionTracking(frm);
		const updates = Object.entries(values)
			.filter(([fieldname, value]) => frm.doc[fieldname] !== value)
			.map(([fieldname, value]) => frm.set_value(fieldname, value));
		return Promise.all(updates);
	}

	function numberOrZero(value) {
		const number = Number(value);
		return Number.isFinite(number) ? number : 0;
	}

	function roundConsumptionWeight(value) {
		const rounded = Number(numberOrZero(value).toFixed(SHEET_CONSUMPTION_PRECISION));
		return Object.is(rounded, -0) ? 0 : rounded;
	}

	function getConsumptionStatus(leftoverWeight) {
		if (leftoverWeight > SHEET_CONSUMPTION_TOLERANCE_KG) {
			return "Short";
		}
		if (leftoverWeight < -SHEET_CONSUMPTION_TOLERANCE_KG) {
			return "Excess";
		}
		return "Balanced";
	}

	function updateSheetWeightAndRedraw(frm) {
		updateSheetWeight(frm)
			.then(() => updateEndPieceWeights(frm))
			.then(() => updateConsumptionTracking(frm))
			.then(() => {
				scheduleSheetLayoutRedraw(frm);
			});
	}

	function updateStripWeightAndRedraw(frm) {
		updateStripWeight(frm)
			.then(() => updateFinishedPartWeights(frm))
			.then(() => updateConsumptionTracking(frm))
			.then(() => {
				scheduleSheetLayoutRedraw(frm);
			});
	}

	function updateConsumptionTrackingAndRedraw(frm) {
		updateConsumptionTracking(frm).then(() => {
			scheduleSheetLayoutRedraw(frm);
		});
	}

	function updateFinishedPartWeightsAndRedraw(frm) {
		updateFinishedPartWeights(frm)
			.then(() => updateConsumptionTracking(frm))
			.then(() => {
				scheduleSheetLayoutRedraw(frm);
			});
	}

	function updatePartsPerSheetAndRedraw(frm) {
		updatePartsPerSheet(frm)
			.then(() => updateFinishedPartWeights(frm))
			.then(() => updateConsumptionTracking(frm))
			.then(() => {
				scheduleSheetLayoutRedraw(frm);
			});
	}

	function updateEndPieceWeightsAndRedraw(frm) {
		updateEndPieceWeights(frm)
			.then(() => updateConsumptionTracking(frm))
			.then(() => {
				scheduleSheetLayoutRedraw(frm);
			});
	}

	frappe.ui.form.on("Sheet Cutting Layout", {
		refresh(frm) {
			loadSheetLayoutCanvas().then(() => {
				ensurePreviewCanvas(frm);
				scheduleSheetLayoutRedraw(frm);
			});
			if (!frm.is_new() && ["Released", "Superseded"].includes(frm.doc.status)) {
				frm.add_custom_button(__("New Version"), () => {
					frappe.call({
						method: "sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.sheet_cutting_layout.create_sheet_cutting_layout_revision",
						args: { name: frm.doc.name },
						callback: (r) => {
							if (r.message) {
								frappe.set_route("Form", "Sheet Cutting Layout", r.message);
							}
						},
					});
				});
			}
		},

		before_workflow_action(frm) {
			frm.sheet_cutting_layout_last_workflow_action = frm.selected_workflow_action;
			return Promise.resolve();
		},

		after_workflow_action(frm) {
			const action =
				frm.sheet_cutting_layout_last_workflow_action || frm.selected_workflow_action;
			frm.sheet_cutting_layout_last_workflow_action = null;
			const stepName = APPROVAL_SNAPSHOT_ACTIONS[action];
			if (!stepName) {
				return Promise.resolve();
			}

			return frm.reload_doc();
		},

		finished_parts_add: updatePartsPerSheetAndRedraw,
		finished_parts_remove: updateConsumptionTrackingAndRedraw,
		end_pieces_add: updateEndPieceWeightsAndRedraw,
		end_pieces_remove: updateConsumptionTrackingAndRedraw,
	});

	frappe.ui.form.on("Sheet Cutting Layout", {
		sheet_thickness_mm: updateSheetWeightAndRedraw,
		sheet_width_mm: updateSheetWeightAndRedraw,
		sheet_length_mm: updateSheetWeightAndRedraw,
		strip_thickness_mm: updateStripWeightAndRedraw,
		strip_width_mm: updateStripWeightAndRedraw,
		strip_length_mm: updateStripWeightAndRedraw,
		parts_per_strip: updatePartsPerSheetAndRedraw,
		no_of_strips: updatePartsPerSheetAndRedraw,
	});

	SHEET_LAYOUT_FIELDS.forEach((fieldname) => {
		frappe.ui.form.on("Sheet Cutting Layout", fieldname, scheduleSheetLayoutRedraw);
	});

	frappe.ui.form.on("Layout Finished Part", {
		finished_part_item: updatePartsPerSheetAndRedraw,
		parts_per_sheet: updateConsumptionTrackingAndRedraw,
		net_weight_per_part_kg: updateFinishedPartWeightsAndRedraw,
		gross_weight_per_part_kg: updateConsumptionTrackingAndRedraw,
		scrap_weight_per_part_kg: scheduleParentRedraw,
	});

	frappe.ui.form.on("Layout End Piece", {
		end_piece_item: scheduleParentRedraw,
		width_mm: updateEndPieceWeightsAndRedraw,
		length_mm: updateEndPieceWeightsAndRedraw,
		weight_kg: updateConsumptionTrackingAndRedraw,
		qty_per_sheet: updateConsumptionTrackingAndRedraw,
		disposition: scheduleParentRedraw,
		used_for_finished_part: scheduleParentRedraw,
	});
})();
