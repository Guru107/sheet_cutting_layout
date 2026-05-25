frappe.provide("sheet_cutting_layout");

(() => {
	"use strict";

	const STEEL_DENSITY_G_PER_CM3 = 7.86;
	const DEFAULT_FLOAT_PRECISION = 6;
	const SHEET_CONSUMPTION_PRECISION = 3;
	const SHEET_CONSUMPTION_TOLERANCE_KG = 0.005;

	const APPROVAL_SNAPSHOT_ACTIONS = {
		"Projects Manager Approves": "Projects Manager Approval",
		"Manufacturing Manager Approves": "Manufacturing Manager Approval",
		"Purchase Approves": "Purchase Approval",
		Reject: "Rejection",
	};

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
		const singleWeight = calculateWeight(
			frm.doc.sheet_thickness_mm,
			row.width_mm,
			row.length_mm
		);
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
		if (
			!frm.doc.raw_material_item ||
			!frm.doc.sheet_thickness_mm ||
			!row.width_mm ||
			!row.length_mm
		) {
			return null;
		}
		return `${frm.doc.raw_material_item}-EP-${formatCodeNumber(
			frm.doc.sheet_thickness_mm
		)}x${formatCodeNumber(row.width_mm)}x${formatCodeNumber(row.length_mm)}`;
	}

	function updateEndPieceItemCodes(frm) {
		const updates = (frm.doc.end_pieces || []).flatMap((row) => {
			if (
				row.disposition !== "Reuse" ||
				row.generated_end_piece_item ||
				row.generated_end_piece_bom
			) {
				return [];
			}
			if (row.end_piece_item_code) {
				return [];
			}
			const suggested = suggestEndPieceItemCode(frm, row);
			if (!suggested) {
				return [];
			}
			return [
				frappe.model.set_value(row.doctype, row.name, "end_piece_item_code", suggested),
			];
		});

		return Promise.all(updates);
	}

	function updateEndPieceItemCodesFromRawMaterial(frm) {
		return updateEndPieceItemCodes(frm);
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
			}, 0) + endPieces.reduce((total, row) => total + numberOrZero(row.weight_kg), 0)
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

	function escapeHtml(value) {
		return String(value ?? "").replace(/[&<>"']/g, (character) => {
			const replacements = {
				"&": "&amp;",
				"<": "&lt;",
				">": "&gt;",
				'"': "&quot;",
				"'": "&#39;",
			};
			return replacements[character];
		});
	}

	function updateSheetWeightAndDerivedFields(frm) {
		return updateSheetWeight(frm)
			.then(() => updateEndPieceWeights(frm))
			.then(() => updateEndPieceItemCodes(frm))
			.then(() => updateConsumptionTracking(frm));
	}

	function updateStripWeightAndDerivedFields(frm) {
		return updateStripWeight(frm)
			.then(() => updateParentGrossWeightPerPart(frm))
			.then(() => updateFinishedPartWeights(frm))
			.then(() => updateConsumptionTracking(frm));
	}

	function updateConsumptionTrackingFields(frm) {
		return updateConsumptionTracking(frm);
	}

	function updateFinishedPartWeightsAndConsumption(frm) {
		return updateFinishedPartWeights(frm).then(() => updateConsumptionTracking(frm));
	}

	function updatePartsPerSheetAndDerivedFields(frm) {
		return updatePartsPerSheet(frm)
			.then(() => updateParentGrossWeightPerPart(frm))
			.then(() => updateFinishedPartWeights(frm))
			.then(() => updateConsumptionTracking(frm));
	}

	function updateEndPieceWeightsAndConsumption(frm) {
		return updateEndPieceWeights(frm)
			.then(() => updateEndPieceItemCodes(frm))
			.then(() => updateConsumptionTracking(frm));
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
					<td>${escapeHtml(row.idx)}</td>
					<td>${escapeHtml(row.end_piece_item_code)}</td>
					<td>${escapeHtml(row.suggested_item_code)}</td>
					<td>${escapeHtml(row.item_status)}</td>
					<td>${escapeHtml(row.used_for_finished_part)}</td>
					<td>${escapeHtml(row.bom_quantity)}</td>
					<td>${escapeHtml(row.raw_material_qty_kg)}</td>
					<td>${escapeHtml(row.bom_scrap_quantity_kg)}</td>
					<td>${escapeHtml(row.bom_status)}</td>
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

		finished_parts_add: updatePartsPerSheetAndDerivedFields,
		finished_parts_remove: updateConsumptionTrackingFields,
		end_pieces_add: updateEndPieceWeightsAndConsumption,
		end_pieces_remove: updateConsumptionTrackingFields,
	});

	frappe.ui.form.on("Sheet Cutting Layout", {
		sheet_thickness_mm: updateSheetWeightAndDerivedFields,
		sheet_width_mm: updateSheetWeightAndDerivedFields,
		sheet_length_mm: updateSheetWeightAndDerivedFields,
		strip_thickness_mm: updateStripWeightAndDerivedFields,
		strip_width_mm: updateStripWeightAndDerivedFields,
		strip_length_mm: updateStripWeightAndDerivedFields,
		parts_per_strip: updatePartsPerSheetAndDerivedFields,
		no_of_strips: updatePartsPerSheetAndDerivedFields,
		raw_material_item: updateEndPieceItemCodesFromRawMaterial,
	});

	frappe.ui.form.on("Layout Finished Part", {
		finished_part_item: updatePartsPerSheetAndDerivedFields,
		parts_per_sheet: updateConsumptionTrackingFields,
		net_weight_per_part_kg: updateFinishedPartWeightsAndConsumption,
		gross_weight_per_part_kg: updateConsumptionTrackingFields,
	});

	frappe.ui.form.on("Layout End Piece", {
		width_mm: updateEndPieceWeightsAndConsumption,
		length_mm: updateEndPieceWeightsAndConsumption,
		weight_kg: updateConsumptionTrackingFields,
		qty_per_sheet: updateEndPieceWeightsAndConsumption,
		disposition: updateEndPieceItemCodesFromRawMaterial,
	});
})();
