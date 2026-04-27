frappe.provide("sheet_cutting_layout");

(() => {
	"use strict";

	const SHEET_LAYOUT_CANVAS_ASSET = "/assets/sheet_cutting_layout/js/sheet_layout_canvas.js";
	const SHEET_LAYOUT_PREVIEW_ID = "sheet-layout-canvas-preview";
	const SHEET_LAYOUT_REDRAW_MS = 200;

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
	];

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
				? window.SheetLayoutCanvas.debounce(() => redrawSheetLayout(frm), SHEET_LAYOUT_REDRAW_MS)
				: frappe.utils.debounce(() => redrawSheetLayout(frm), SHEET_LAYOUT_REDRAW_MS);
		}
		frm.sheet_layout_redraw();
	}

	function scheduleParentRedraw(frm) {
		scheduleSheetLayoutRedraw(frm);
	}

	frappe.ui.form.on("Sheet Cutting Layout", {
		refresh(frm) {
			loadSheetLayoutCanvas().then(() => {
				ensurePreviewCanvas(frm);
				scheduleSheetLayoutRedraw(frm);
			});
		},

		finished_parts_add: scheduleSheetLayoutRedraw,
		finished_parts_remove: scheduleSheetLayoutRedraw,
		end_pieces_add: scheduleSheetLayoutRedraw,
		end_pieces_remove: scheduleSheetLayoutRedraw,
	});

	SHEET_LAYOUT_FIELDS.forEach((fieldname) => {
		frappe.ui.form.on("Sheet Cutting Layout", fieldname, scheduleSheetLayoutRedraw);
	});

	frappe.ui.form.on("Layout Finished Part", {
		finished_part_item: scheduleParentRedraw,
		parts_per_sheet: scheduleParentRedraw,
		gross_weight_per_part_kg: scheduleParentRedraw,
		scrap_weight_per_part_kg: scheduleParentRedraw,
	});

	frappe.ui.form.on("Layout End Piece", {
		end_piece_item: scheduleParentRedraw,
		weight_kg: scheduleParentRedraw,
		qty_per_sheet: scheduleParentRedraw,
		disposition: scheduleParentRedraw,
		used_for_finished_part: scheduleParentRedraw,
	});
})();
