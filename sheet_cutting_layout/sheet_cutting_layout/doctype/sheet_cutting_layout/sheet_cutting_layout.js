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
		"gross_weight_per_part_kg",
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

	function calculateParentGrossWeightPerPart(frm) {
		const stripWeight = Number(frm.doc.weight_of_strip_kg);
		const partsPerStrip = Number(frm.doc.parts_per_strip);
		if (!(stripWeight >= 0 && partsPerStrip > 0)) {
			return null;
		}

		return Number((stripWeight / partsPerStrip).toFixed(getCalculationPrecision()));
	}

	function updateParentGrossWeightPerPart(frm) {
		const grossWeight = calculateParentGrossWeightPerPart(frm);
		if (grossWeight === null || frm.doc.gross_weight_per_part_kg === grossWeight) {
			return Promise.resolve();
		}

		return frm.set_value("gross_weight_per_part_kg", grossWeight);
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
		const singleWeight = calculateWeight(frm.doc.sheet_thickness_mm, row.width_mm, row.length_mm);
		if (singleWeight === null) {
			return null;
		}
		return Number(
			(singleWeight * numberOrZero(row.qty_per_sheet || 1)).toFixed(
				getCalculationPrecision()
			)
		);
	}

	function formatCodeNumber(value) {
		const number = Number(value);
		if (!Number.isFinite(number)) {
			return "";
		}
		if (Number.isInteger(number)) {
			return String(number);
		}
		return number.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
	}

	function suggestEndPieceItemCode(frm, row) {
		if (!frm.doc.raw_material_item || !frm.doc.sheet_thickness_mm || !row.width_mm || !row.length_mm) {
			return null;
		}
		return `${frm.doc.raw_material_item}-EP-${formatCodeNumber(frm.doc.sheet_thickness_mm)}x${formatCodeNumber(row.width_mm)}x${formatCodeNumber(row.length_mm)}`;
	}

	function updateEndPieceItemCodes(frm) {
		const updates = (frm.doc.end_pieces || []).flatMap((row) => {
			if (row.disposition !== "Reuse" || row.generated_end_piece_item || row.generated_end_piece_bom) {
				return [];
			}
			if (row.end_piece_item_code) {
				return [];
			}
			const suggested = suggestEndPieceItemCode(frm, row);
			if (!suggested) {
				return [];
			}
			return [frappe.model.set_value(row.doctype, row.name, "end_piece_item_code", suggested)];
		});

		return Promise.all(updates);
	}

	function updateEndPieceItemCodesAndRedraw(frm) {
		updateEndPieceItemCodes(frm).then(() => {
			scheduleSheetLayoutRedraw(frm);
		});
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
					(total, row) => total + numberOrZero(row.weight_kg),
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
			.then(() => updateEndPieceItemCodes(frm))
			.then(() => updateConsumptionTracking(frm))
			.then(() => {
				scheduleSheetLayoutRedraw(frm);
			});
	}

	function updateStripWeightAndRedraw(frm) {
		updateStripWeight(frm)
			.then(() => updateParentGrossWeightPerPart(frm))
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
			.then(() => updateParentGrossWeightPerPart(frm))
			.then(() => updateFinishedPartWeights(frm))
			.then(() => updateConsumptionTracking(frm))
			.then(() => {
				scheduleSheetLayoutRedraw(frm);
			});
	}

	function updateEndPieceWeightsAndRedraw(frm) {
		updateEndPieceWeights(frm)
			.then(() => updateEndPieceItemCodes(frm))
			.then(() => updateConsumptionTracking(frm))
			.then(() => {
				scheduleSheetLayoutRedraw(frm);
			});
	}

	function hasRequiredEndPiecePreviewInputs(frm) {
		return Boolean(frm.doc.raw_material_item && frm.doc.sheet_thickness_mm);
	}

	function addEndPieceBomButtons(frm) {
		const hasReusableEndPieces = (frm.doc.end_pieces || []).some(
			(row) => row.disposition === "Reuse"
		);
		if (!hasReusableEndPieces || frm.is_new() || !hasRequiredEndPiecePreviewInputs(frm)) {
			return;
		}

		frm.add_custom_button(__("Preview End Piece Items"), () => previewEndPieceItems(frm));
		if (frm.doc.status === "Released" && frm.doc.end_piece_bom_status === "Pending") {
			frm.add_custom_button(__("Generate End Piece BOMs"), () => generateEndPieceBoms(frm));
		}
	}

	function previewEndPieceItems(frm) {
		frappe.call({
			method: "sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.sheet_cutting_layout.preview_sheet_cutting_layout_end_piece_boms",
			args: { name: frm.doc.name },
			callback: (r) => {
				showEndPiecePreviewDialog(r.message || []);
			},
		});
	}

	function generateEndPieceBoms(frm) {
		frappe.call({
			method: "sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.sheet_cutting_layout.generate_sheet_cutting_layout_end_piece_boms",
			args: { name: frm.doc.name },
			freeze: true,
			freeze_message: __("Generating End Piece BOMs"),
			callback: () => frm.reload_doc(),
		});
	}

	function showEndPiecePreviewDialog(rows) {
		const dialog = new frappe.ui.Dialog({
			title: __("Preview End Piece Items"),
			fields: [
				{
					fieldname: "preview",
					fieldtype: "HTML",
					options: buildEndPiecePreviewHtml(rows),
				},
			],
			primary_action_label: __("Close"),
			primary_action() {
				dialog.hide();
			},
		});
		dialog.show();
	}

	function buildEndPiecePreviewHtml(rows) {
		if (!rows.length) {
			return `<p>${__("No reusable end pieces found.")}</p>`;
		}
		const body = rows
			.map(
				(row) => `<tr>
					<td>${frappe.utils.escape_html(String(row.idx || ""))}</td>
					<td>${frappe.utils.escape_html(row.end_piece_item_code || "")}</td>
					<td>${frappe.utils.escape_html(row.suggested_item_code || "")}</td>
					<td>${frappe.utils.escape_html(row.item_status || "")}</td>
					<td>${frappe.utils.escape_html(row.used_for_finished_part || "")}</td>
					<td>${frappe.utils.escape_html(String(row.bom_quantity ?? ""))}</td>
					<td>${frappe.utils.escape_html(String(row.raw_material_qty_kg ?? ""))}</td>
					<td>${frappe.utils.escape_html(String(row.bom_scrap_quantity_kg ?? ""))}</td>
					<td>${frappe.utils.escape_html(row.bom_status || "")}</td>
				</tr>`
			)
			.join("");

		return `<table class="table table-bordered">
			<thead><tr>
				<th>${__("Row")}</th>
				<th>${__("Current Item Code")}</th>
				<th>${__("Suggested Item Code")}</th>
				<th>${__("Item Status")}</th>
				<th>${__("Used For")}</th>
				<th>${__("BOM Qty")}</th>
				<th>${__("Raw Qty Kg")}</th>
				<th>${__("Scrap Qty Kg")}</th>
				<th>${__("BOM Status")}</th>
			</tr></thead>
			<tbody>${body}</tbody>
		</table>`;
	}

	frappe.ui.form.on("Sheet Cutting Layout", {
		refresh(frm) {
			loadSheetLayoutCanvas().then(() => {
				ensurePreviewCanvas(frm);
				scheduleSheetLayoutRedraw(frm);
			});
			addEndPieceBomButtons(frm);
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
		raw_material_item: updateEndPieceItemCodesAndRedraw,
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
		end_piece_item_code: scheduleParentRedraw,
		width_mm: updateEndPieceWeightsAndRedraw,
		length_mm: updateEndPieceWeightsAndRedraw,
		weight_kg: updateConsumptionTrackingAndRedraw,
		qty_per_sheet: updateEndPieceWeightsAndRedraw,
		disposition: scheduleParentRedraw,
		scrap_item: scheduleParentRedraw,
		used_for_finished_part: scheduleParentRedraw,
		bom_quantity: scheduleParentRedraw,
		bom_scrap_quantity_kg: scheduleParentRedraw,
		generated_end_piece_item: scheduleParentRedraw,
		generated_end_piece_bom: scheduleParentRedraw,
	});
})();
