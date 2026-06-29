frappe.provide("sheet_cutting_layout");

(() => {
	"use strict";

	const STEEL_DENSITY_G_PER_CM3 = 7.86;
	const DEFAULT_FLOAT_PRECISION = 6;
	const SHEET_CONSUMPTION_PRECISION = 3;
	const SHEET_CONSUMPTION_TOLERANCE_KG = 0.005;

	const APPROVAL_SNAPSHOT_ACTIONS = {
		"Project Manager Approves": "Project Manager Approval",
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

	function syncStripThicknessFromSheet(frm) {
		if (frm.doc.strip_thickness_mm === frm.doc.sheet_thickness_mm) {
			return Promise.resolve();
		}

		return frm.set_value("strip_thickness_mm", frm.doc.sheet_thickness_mm);
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

	function calculateParentScrapWeightPerPart(frm) {
		const grossWeight = Number(frm.doc.gross_weight_per_part_kg);
		const netWeight = Number(frm.doc.net_weight_per_part_kg);
		if (!(grossWeight >= 0) || !Number.isFinite(netWeight)) {
			return null;
		}

		return Number((grossWeight - netWeight).toFixed(getCalculationPrecision()));
	}

	function updateParentScrapWeightPerPart(frm) {
		const scrapWeight = calculateParentScrapWeightPerPart(frm);
		if (scrapWeight === null || frm.doc.scrap_weight_per_part_kg === scrapWeight) {
			return Promise.resolve();
		}

		return frm.set_value("scrap_weight_per_part_kg", scrapWeight);
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

	function calculateEndPieceStripWeight(frm, row) {
		return calculateWeight(
			frm.doc.sheet_thickness_mm,
			row.strip_width_mm,
			row.strip_length_mm
		);
	}

	function calculateEndPieceGrossWeightPerPart(row) {
		const weight = Number(row.strip_weight_kg);
		const bomQuantity = Number(row.bom_quantity);
		if (!(weight >= 0 && bomQuantity > 0)) {
			return null;
		}

		return Number((weight / bomQuantity).toFixed(getCalculationPrecision()));
	}

	function calculateEndPieceScrapWeightPerPart(row) {
		const grossWeight = Number(row.gross_weight_per_part_kg);
		const netWeight = Number(row.net_weight_per_part_kg);
		if (!(grossWeight >= 0) || !Number.isFinite(netWeight)) {
			return null;
		}

		return Number((grossWeight - netWeight).toFixed(getCalculationPrecision()));
	}

	function calculateEndPieceBomScrapQuantity(row) {
		const scrapWeight = Number(row.scrap_weight_per_part_kg);
		const bomQuantity = Number(row.bom_quantity);
		if (!(scrapWeight >= 0 && bomQuantity > 0)) {
			return null;
		}

		return Number((scrapWeight * bomQuantity).toFixed(getCalculationPrecision()));
	}

	function hasValue(value) {
		return value !== null && value !== undefined && value !== "";
	}

	function hasWritePermission(frm) {
		if (typeof frm.has_perm === "function") {
			return frm.has_perm("write");
		}
		const permissions = Array.isArray(frm.perm) ? frm.perm : [];
		return permissions.some((entry) => Boolean(entry && entry.write));
	}

	function clearStaleEndPieceDispositionFields(cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row) {
			return Promise.resolve();
		}

		const updates = [];
		if (row.disposition === "Reuse") {
			return Promise.all(updates);
		}

		if (row.disposition !== "Scrap") {
			return Promise.resolve();
		}

		if (row.used_for_finished_part) {
			updates.push(frappe.model.set_value(cdt, cdn, "used_for_finished_part", ""));
		}
		if (hasValue(row.bom_quantity)) {
			updates.push(frappe.model.set_value(cdt, cdn, "bom_quantity", null));
		}
		if (hasValue(row.net_weight_per_part_kg)) {
			updates.push(frappe.model.set_value(cdt, cdn, "net_weight_per_part_kg", null));
		}
		if (hasValue(row.gross_weight_per_part_kg)) {
			updates.push(frappe.model.set_value(cdt, cdn, "gross_weight_per_part_kg", null));
		}
		if (hasValue(row.scrap_weight_per_part_kg)) {
			updates.push(frappe.model.set_value(cdt, cdn, "scrap_weight_per_part_kg", null));
		}
		if (hasValue(row.bom_scrap_quantity_kg)) {
			updates.push(frappe.model.set_value(cdt, cdn, "bom_scrap_quantity_kg", null));
		}
		if (hasValue(row.strip_width_mm)) {
			updates.push(frappe.model.set_value(cdt, cdn, "strip_width_mm", null));
		}
		if (hasValue(row.strip_length_mm)) {
			updates.push(frappe.model.set_value(cdt, cdn, "strip_length_mm", null));
		}
		if (hasValue(row.strip_weight_kg)) {
			updates.push(frappe.model.set_value(cdt, cdn, "strip_weight_kg", null));
		}
		return Promise.all(updates);
	}

	function updatePartsPerSheet(frm) {
		const partsPerSheet = calculatePartsPerSheet(frm);
		if (partsPerSheet === null) {
			return Promise.resolve();
		}

		if (frm.doc.parts_per_sheet === partsPerSheet) {
			return Promise.resolve();
		}

		return frm.set_value("parts_per_sheet", partsPerSheet);
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

	function updateEndPieceStripWeights(frm) {
		const updates = (frm.doc.end_pieces || []).flatMap((row) => {
			if (row.disposition !== "Reuse") {
				return [];
			}

			const rowUpdates = [];
			const setRowValue = (fieldname, value) => {
				if (row[fieldname] !== value) {
					rowUpdates.push(
						frappe.model.set_value(row.doctype, row.name, fieldname, value)
					);
				}
			};

			if (!hasValue(row.strip_width_mm) && hasValue(row.width_mm)) {
				setRowValue("strip_width_mm", row.width_mm);
			}
			if (!hasValue(row.strip_length_mm) && hasValue(row.length_mm)) {
				setRowValue("strip_length_mm", row.length_mm);
			}

			const stripWeight = calculateEndPieceStripWeight(frm, {
				...row,
				strip_width_mm: hasValue(row.strip_width_mm) ? row.strip_width_mm : row.width_mm,
				strip_length_mm: hasValue(row.strip_length_mm)
					? row.strip_length_mm
					: row.length_mm,
			});
			if (stripWeight !== null) {
				setRowValue("strip_weight_kg", stripWeight);
			}
			return rowUpdates;
		});

		return Promise.all(updates);
	}

	function updateEndPieceReuseWeights(frm) {
		const updates = (frm.doc.end_pieces || []).flatMap((row) => {
			if (row.disposition !== "Reuse") {
				return [];
			}

			const rowUpdates = [];
			const setRowValue = (fieldname, value) => {
				if (row[fieldname] !== value) {
					rowUpdates.push(
						frappe.model.set_value(row.doctype, row.name, fieldname, value)
					);
				}
			};
			const grossWeight = calculateEndPieceGrossWeightPerPart(row);
			if (grossWeight === null) {
				setRowValue("gross_weight_per_part_kg", null);
				setRowValue("scrap_weight_per_part_kg", null);
				setRowValue("bom_scrap_quantity_kg", null);
				return rowUpdates;
			}

			setRowValue("gross_weight_per_part_kg", grossWeight);
			const scrapWeight = calculateEndPieceScrapWeightPerPart({
				...row,
				gross_weight_per_part_kg: grossWeight,
			});
			if (scrapWeight === null) {
				setRowValue("scrap_weight_per_part_kg", null);
				setRowValue("bom_scrap_quantity_kg", null);
				return rowUpdates;
			}

			setRowValue("scrap_weight_per_part_kg", scrapWeight);
			const bomScrapQuantity = calculateEndPieceBomScrapQuantity({
				...row,
				scrap_weight_per_part_kg: scrapWeight,
			});
			if (bomScrapQuantity === null) {
				setRowValue("bom_scrap_quantity_kg", null);
			} else {
				setRowValue("bom_scrap_quantity_kg", bomScrapQuantity);
			}
			return rowUpdates;
		});

		return Promise.all(updates);
	}

	function calculateConsumptionTracking(frm) {
		const endPieces = frm.doc.end_pieces || [];
		const consumedWeight = roundConsumptionWeight(
			numberOrZero(frm.doc.gross_weight_per_part_kg) *
				numberOrZero(frm.doc.parts_per_sheet) +
				endPieces.reduce((total, row) => total + endPieceConsumedWeight(row), 0)
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

	function endPieceConsumedWeight(row) {
		if (row.disposition === "Reuse") {
			return numberOrZero(row.strip_weight_kg);
		}
		return numberOrZero(row.weight_kg);
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

	function updateSheetWeightAndDerivedFields(frm) {
		return syncStripThicknessFromSheet(frm)
			.then(() => updateSheetWeight(frm))
			.then(() => updateStripWeight(frm))
			.then(() => updateParentGrossWeightPerPart(frm))
			.then(() => updateParentScrapWeightPerPart(frm))
			.then(() => updateEndPieceWeights(frm))
			.then(() => updateEndPieceStripWeights(frm))
			.then(() => updateEndPieceReuseWeights(frm))
			.then(() => updateConsumptionTracking(frm));
	}

	function updateStripWeightAndDerivedFields(frm) {
		return updateStripWeight(frm)
			.then(() => updateParentGrossWeightPerPart(frm))
			.then(() => updateParentScrapWeightPerPart(frm))
			.then(() => updateConsumptionTracking(frm));
	}

	function updateConsumptionTrackingFields(frm) {
		return updateConsumptionTracking(frm);
	}

	function updateParentWeightsAndConsumption(frm) {
		return updateParentScrapWeightPerPart(frm).then(() => updateConsumptionTracking(frm));
	}

	function updatePartsPerSheetAndDerivedFields(frm) {
		return updatePartsPerSheet(frm)
			.then(() => updateParentGrossWeightPerPart(frm))
			.then(() => updateParentScrapWeightPerPart(frm))
			.then(() => updateConsumptionTracking(frm));
	}

	function updateEndPieceWeightsAndConsumption(frm) {
		return updateEndPieceWeights(frm)
			.then(() => updateEndPieceStripWeights(frm))
			.then(() => updateEndPieceReuseWeights(frm))
			.then(() => updateConsumptionTracking(frm));
	}

	function updateEndPieceReuseWeightsAndConsumption(frm) {
		return updateEndPieceReuseWeights(frm).then(() => updateConsumptionTracking(frm));
	}

	function updateEndPieceDispositionAndDerivedFields(frm, cdt, cdn) {
		return clearStaleEndPieceDispositionFields(cdt, cdn).then(() =>
			updateEndPieceWeightsAndConsumption(frm)
		);
	}

	function updateLhRhFields(frm) {
		if (frm.doc.is_lh_rh) {
			if (!frm.doc.orientation) {
				return frm.set_value("orientation", "LH");
			}
			return Promise.resolve();
		}

		const updates = [];
		if (frm.doc.orientation) {
			updates.push(frm.set_value("orientation", ""));
		}
		if (frm.doc.twin_finished_part) {
			updates.push(frm.set_value("twin_finished_part", ""));
		}
		return Promise.all(updates);
	}

	function updateOrientationDescription(frm) {
		const finishedPartCode = frm.doc.finished_part_code || "finished_part_code";
		frm.set_df_property(
			"orientation",
			"description",
			`Set the orientation for ${finishedPartCode}`
		);
	}

	function addEndPieceBomButtons(frm) {
		const hasReusableEndPieces = (frm.doc.end_pieces || []).some(
			(row) => row.disposition === "Reuse"
		);
		if (!hasReusableEndPieces || frm.is_new() || !hasWritePermission(frm)) {
			return;
		}
		if (frm.doc.workflow_status === "Released" && frm.doc.end_piece_bom_status === "Pending") {
			frm.add_custom_button(__("Generate End Piece BOMs"), () => generateEndPieceBoms(frm));
		}
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

	function addDownloadLayoutButton(frm) {
		if (frm.is_new()) {
			return;
		}
		frm.add_custom_button(__("Download Layout (Excel)"), () => {
			const method =
				"sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout." +
				"sheet_cutting_layout.download_sheet_cutting_layout";
			const url = `/api/method/${method}?name=${encodeURIComponent(frm.doc.name)}`;
			window.open(url, "_blank");
		});
	}

	function ignoreBomInGenericCancelAll(frm) {
		frm.ignore_doctypes_on_cancel_all = Array.from(
			new Set([...(frm.ignore_doctypes_on_cancel_all || []), "BOM"])
		);
	}

	frappe.ui.form.on("Sheet Cutting Layout", {
		refresh(frm) {
			ignoreBomInGenericCancelAll(frm);
			updateOrientationDescription(frm);
			addEndPieceBomButtons(frm);
			addDownloadLayoutButton(frm);
			if (!frm.is_new() && ["Released", "Superseded"].includes(frm.doc.workflow_status)) {
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
		net_weight_per_part_kg: updateParentWeightsAndConsumption,
		finished_part_code: updateOrientationDescription,
		is_lh_rh: updateLhRhFields,
	});

	frappe.ui.form.on("Layout End Piece", {
		width_mm: updateEndPieceWeightsAndConsumption,
		length_mm: updateEndPieceWeightsAndConsumption,
		weight_kg: updateConsumptionTrackingFields,
		strip_width_mm: updateEndPieceWeightsAndConsumption,
		strip_length_mm: updateEndPieceWeightsAndConsumption,
		strip_weight_kg: updateEndPieceReuseWeightsAndConsumption,
		disposition: updateEndPieceDispositionAndDerivedFields,
		bom_quantity: updateEndPieceWeightsAndConsumption,
		net_weight_per_part_kg: updateEndPieceWeightsAndConsumption,
	});
})();
