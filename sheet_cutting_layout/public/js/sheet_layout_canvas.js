(function () {
	"use strict";

	const DEFAULT_WIDTH = 860;
	const DEFAULT_HEIGHT = 420;

	function numberOrNull(value) {
		const number = Number(value);
		return Number.isFinite(number) ? number : null;
	}

	function positiveNumber(value) {
		const number = numberOrNull(value);
		return number !== null && number > 0 ? number : null;
	}

	function positiveInteger(value) {
		const number = numberOrNull(value);
		return number !== null && Number.isInteger(number) && number > 0 ? number : null;
	}

	function markerValue(value) {
		return typeof value === "number" && !Number.isFinite(value) ? String(value) : value;
	}

	function marker(field, value, message) {
		return { field, value: markerValue(value), message };
	}

	function buildPayloadFromDoc(doc) {
		const invalidMarkers = [];
		const sheetWidth = positiveNumber(doc.sheet_width_mm);
		const sheetLength = positiveNumber(doc.sheet_length_mm);
		const sheetThickness = positiveNumber(doc.sheet_thickness_mm);
		const stripWidth = positiveNumber(doc.strip_width_mm);
		const stripLength = positiveNumber(doc.strip_length_mm);
		const noOfStrips = positiveInteger(doc.no_of_strips);
		const partsPerStrip = positiveInteger(doc.parts_per_strip);
		const partsPerSheet = positiveInteger(doc.parts_per_sheet);

		[
			["sheet_width_mm", sheetWidth, doc.sheet_width_mm],
			["sheet_length_mm", sheetLength, doc.sheet_length_mm],
			["sheet_thickness_mm", sheetThickness, doc.sheet_thickness_mm],
			["strip_width_mm", stripWidth, doc.strip_width_mm],
			["strip_length_mm", stripLength, doc.strip_length_mm],
			["no_of_strips", noOfStrips, doc.no_of_strips],
			["parts_per_strip", partsPerStrip, doc.parts_per_strip],
			["parts_per_sheet", partsPerSheet, doc.parts_per_sheet],
		].forEach(([field, value, original]) => {
			if (value === null) {
				invalidMarkers.push(marker(field, original, "must be greater than zero"));
			}
		});

		const finishedParts = doc.finished_parts || [];
		const endPieces = doc.end_pieces || [];

		return {
			sheet_dimensions: {
				width_mm: sheetWidth,
				length_mm: sheetLength,
				thickness_mm: sheetThickness,
			},
			strips: buildStripZones(sheetWidth, sheetLength, stripWidth, stripLength, noOfStrips),
			part_zones: buildPartZones(
				finishedParts,
				sheetWidth,
				sheetLength,
				stripLength,
				noOfStrips,
				partsPerStrip,
				partsPerSheet,
				invalidMarkers
			),
			end_piece_zones: buildEndPieceZones(
				endPieces,
				sheetWidth,
				sheetLength,
				stripLength,
				noOfStrips,
				invalidMarkers
			),
			summary: buildSummary(finishedParts, endPieces, invalidMarkers),
			invalid_markers: invalidMarkers,
		};
	}

	function buildStripZones(sheetWidth, sheetLength, stripWidth, stripLength, noOfStrips) {
		if (!sheetWidth || !sheetLength || !noOfStrips) {
			return [];
		}

		const width = stripWidth || sheetWidth;
		const length = stripLength || sheetLength / noOfStrips;
		return Array.from({ length: noOfStrips }, (_, index) => ({
			index: index + 1,
			x_mm: 0,
			y_mm: index * length,
			width_mm: width,
			length_mm: length,
		}));
	}

	function buildPartZones(
		finishedParts,
		sheetWidth,
		sheetLength,
		stripLength,
		noOfStrips,
		partsPerStrip,
		partsPerSheet,
		invalidMarkers
	) {
		if (!sheetWidth || !sheetLength) {
			return [];
		}

		const zones = [];
		const rowsFromStrips = noOfStrips || 1;
		const columns = partsPerStrip || Math.max(1, Math.ceil((partsPerSheet || 1) / rowsFromStrips));
		const defaultParts = (noOfStrips || 0) * (partsPerStrip || 0) || partsPerSheet || 1;

		finishedParts.forEach((row, rowIndex) => {
			const rowParts = positiveInteger(row.parts_per_sheet);
			if (!rowParts) {
				invalidMarkers.push(marker(`finished_parts[${rowIndex}].parts_per_sheet`, row.parts_per_sheet, "must be greater than zero"));
			}

			const partCount = rowParts || defaultParts;
			const rows = noOfStrips || Math.max(1, Math.ceil(partCount / columns));
			const cellWidth = sheetWidth / columns;
			const cellLength = stripLength && noOfStrips ? stripLength : sheetLength / rows;

			for (let index = 0; index < partCount; index += 1) {
				zones.push({
					finished_part_item: row.finished_part_item || "",
					index: index + 1,
					x_mm: (index % columns) * cellWidth,
					y_mm: Math.floor(index / columns) * cellLength,
					width_mm: cellWidth,
					length_mm: cellLength,
				});
			}
		});

		return zones;
	}

	function buildEndPieceZones(endPieces, sheetWidth, sheetLength, stripLength, noOfStrips, invalidMarkers) {
		const width = sheetWidth || 1;
		const length = sheetLength || 1;
		const usedLength = stripLength && noOfStrips ? stripLength * noOfStrips : 0;
		const remnantLength = Math.max(0, length - usedLength);
		const zoneWidth = width / Math.max(1, endPieces.length);

		return endPieces.map((row, index) => {
			const weight = numberOrNull(row.weight_kg);
			const qty = positiveNumber(row.qty_per_sheet);
			if (weight === null || weight < 0) {
				invalidMarkers.push(marker(`end_pieces[${index}].weight_kg`, row.weight_kg, "must be non-negative"));
			}
			if (!qty) {
				invalidMarkers.push(marker(`end_pieces[${index}].qty_per_sheet`, row.qty_per_sheet, "must be greater than zero"));
			}

			return {
				end_piece_item: row.end_piece_item || null,
				weight_kg: weight !== null && weight >= 0 ? weight : null,
				qty_per_sheet: qty,
				disposition: row.disposition || null,
				used_for_finished_part: row.used_for_finished_part || null,
				x_mm: index * zoneWidth,
				y_mm: usedLength,
				width_mm: zoneWidth,
				length_mm: remnantLength > 0 ? remnantLength : length / Math.max(1, endPieces.length),
			};
		});
	}

	function buildSummary(finishedParts, endPieces, invalidMarkers) {
		let totalGross = 0;
		let totalProcessScrap = 0;
		let totalEndPiece = 0;

		endPieces.forEach((row) => {
			const weight = numberOrNull(row.weight_kg);
			const qty = numberOrNull(row.qty_per_sheet);
			if (weight !== null && qty !== null && weight >= 0 && qty > 0) {
				totalEndPiece += weight * qty;
			}
		});

		finishedParts.forEach((row, rowIndex) => {
			const parts = positiveInteger(row.parts_per_sheet);
			const gross = numberOrNull(row.gross_weight_per_part_kg);
			const scrap = numberOrNull(row.scrap_weight_per_part_kg);

			if (!parts || gross === null || gross < 0 || scrap === null || scrap < 0) {
				if (gross === null || gross < 0) {
					invalidMarkers.push(marker(`finished_parts[${rowIndex}].gross_weight_per_part_kg`, row.gross_weight_per_part_kg, "must be non-negative"));
				}
				if (scrap === null || scrap < 0) {
					invalidMarkers.push(marker(`finished_parts[${rowIndex}].scrap_weight_per_part_kg`, row.scrap_weight_per_part_kg, "must be non-negative"));
				}
				return;
			}

			totalGross += gross * parts;
			totalProcessScrap += scrap * parts;
		});

		return {
			total_gross_weight_kg: totalGross,
			total_process_scrap_weight_kg: totalProcessScrap,
			total_end_piece_weight_kg: totalEndPiece,
			total_scrap_weight_kg: totalProcessScrap + totalEndPiece,
			derived_fg_estimate_kg: totalGross - totalProcessScrap - totalEndPiece,
		};
	}

	function debounce(fn, wait) {
		let timeout = null;
		return function debounced(...args) {
			window.clearTimeout(timeout);
			timeout = window.setTimeout(() => fn.apply(this, args), wait);
		};
	}

	function render(canvas, payload) {
		const context = canvas.getContext("2d");
		if (!context) {
			return;
		}

		const cssWidth = canvas.clientWidth || DEFAULT_WIDTH;
		const cssHeight = canvas.clientHeight || DEFAULT_HEIGHT;
		const ratio = window.devicePixelRatio || 1;
		if (canvas.width !== Math.floor(cssWidth * ratio) || canvas.height !== Math.floor(cssHeight * ratio)) {
			canvas.width = Math.floor(cssWidth * ratio);
			canvas.height = Math.floor(cssHeight * ratio);
		}
		context.setTransform(ratio, 0, 0, ratio, 0, 0);
		context.clearRect(0, 0, cssWidth, cssHeight);

		const sheet = payload.sheet_dimensions || {};
		const sheetWidth = sheet.width_mm || 1;
		const sheetLength = sheet.length_mm || 1;
		const padding = 28;
		const depth = 8;
		const scale = Math.min((cssWidth - padding * 2 - depth) / sheetWidth, (cssHeight - padding * 2 - depth - 34) / sheetLength);
		const originX = padding;
		const originY = padding + depth;
		const width = sheetWidth * scale;
		const length = sheetLength * scale;

		drawSheetBase(context, originX, originY, width, length, depth);
		drawZones(context, payload.strips || [], originX, originY, scale, "#7895b2", "rgba(120, 149, 178, 0.16)");
		drawZones(context, payload.end_piece_zones || [], originX, originY, scale, "#b6633b", "rgba(182, 99, 59, 0.32)");
		drawDimensionMarkers(context, payload, originX, originY, width, length, scale);
		drawInvalidMarkers(context, payload.invalid_markers || [], cssWidth, cssHeight);
		drawSummary(context, payload.summary || {}, padding, cssHeight - 18);
	}

	function drawSheetBase(context, x, y, width, length, depth) {
		context.fillStyle = "#d8dde3";
		context.strokeStyle = "#66717f";
		context.lineWidth = 1;
		context.beginPath();
		context.moveTo(x, y);
		context.lineTo(x + width, y);
		context.lineTo(x + width + depth, y - depth);
		context.lineTo(x + depth, y - depth);
		context.closePath();
		context.fill();
		context.stroke();

		context.fillStyle = "#f5f7f9";
		context.strokeStyle = "#4f5965";
		context.fillRect(x, y, width, length);
		context.strokeRect(x, y, width, length);

		context.fillStyle = "#b8c0ca";
		context.beginPath();
		context.moveTo(x + width, y);
		context.lineTo(x + width + depth, y - depth);
		context.lineTo(x + width + depth, y + length - depth);
		context.lineTo(x + width, y + length);
		context.closePath();
		context.fill();
		context.stroke();
	}

	function drawZones(context, zones, originX, originY, scale, stroke, fill) {
		context.save();
		context.strokeStyle = stroke;
		context.fillStyle = fill;
		context.lineWidth = 1;
		zones.forEach((zone) => {
			const x = originX + (zone.x_mm || 0) * scale;
			const y = originY + (zone.y_mm || 0) * scale;
			const width = Math.max(2, (zone.width_mm || 0) * scale);
			const length = Math.max(2, (zone.length_mm || 0) * scale);
			context.fillRect(x, y, width, length);
			context.strokeRect(x, y, width, length);
		});
		context.restore();
	}

	function drawDimensionMarkers(context, payload, originX, originY, width, length, scale) {
		const sheet = payload.sheet_dimensions || {};
		const strips = payload.strips || [];
		const endPieces = payload.end_piece_zones || [];
		const firstStrip = strips[0];
		const firstEndPiece = endPieces[0];

		context.save();
		context.strokeStyle = "#26313f";
		context.fillStyle = "#26313f";
		context.lineWidth = 1;
		context.font = "12px system-ui, sans-serif";
		context.textAlign = "center";
		context.textBaseline = "middle";

		if (sheet.width_mm) {
			drawHorizontalDimension(
				context,
				originX,
				originX + width,
				originY - 12,
				formatDimension(sheet.width_mm),
				-7
			);
		}

		if (firstStrip && firstStrip.length_mm) {
			const stripY = originY + (firstStrip.y_mm || 0) * scale;
			const stripLength = firstStrip.length_mm * scale;
			drawVerticalDimension(
				context,
				originX - 10,
				stripY,
				stripY + stripLength,
				formatDimension(firstStrip.length_mm),
				-8
			);
		}

		if (firstEndPiece && firstEndPiece.length_mm) {
			const endPieceY = originY + (firstEndPiece.y_mm || 0) * scale;
			const endPieceLength = firstEndPiece.length_mm * scale;
			drawVerticalDimension(
				context,
				originX + width + 10,
				endPieceY,
				Math.min(originY + length, endPieceY + endPieceLength),
				formatDimension(firstEndPiece.length_mm),
				8
			);
		}

		endPieces.forEach((zone) => {
			if (!zone.width_mm) {
				return;
			}
			const x = originX + (zone.x_mm || 0) * scale;
			const zoneWidth = zone.width_mm * scale;
			const y = originY + length + 12;
			drawHorizontalDimension(context, x, x + zoneWidth, y, formatDimension(zone.width_mm), 8);
		});

		context.restore();
	}

	function drawHorizontalDimension(context, x1, x2, y, label, labelOffset) {
		context.beginPath();
		context.moveTo(x1, y - 4);
		context.lineTo(x1, y + 4);
		context.moveTo(x1, y);
		context.lineTo(x2, y);
		context.moveTo(x2, y - 4);
		context.lineTo(x2, y + 4);
		context.stroke();
		context.fillText(label, (x1 + x2) / 2, y + labelOffset);
	}

	function drawVerticalDimension(context, x, y1, y2, label, labelOffset) {
		context.beginPath();
		context.moveTo(x - 4, y1);
		context.lineTo(x + 4, y1);
		context.moveTo(x, y1);
		context.lineTo(x, y2);
		context.moveTo(x - 4, y2);
		context.lineTo(x + 4, y2);
		context.stroke();
		context.save();
		context.translate(x + labelOffset, (y1 + y2) / 2);
		context.rotate(-Math.PI / 2);
		context.fillText(label, 0, 0);
		context.restore();
	}

	function drawInvalidMarkers(context, markers, width, height) {
		if (!markers.length) {
			return;
		}

		context.save();
		context.fillStyle = "#b42318";
		context.strokeStyle = "#b42318";
		context.lineWidth = 2;
		context.beginPath();
		context.moveTo(width - 40, 22);
		context.lineTo(width - 22, 52);
		context.lineTo(width - 58, 52);
		context.closePath();
		context.stroke();
		context.font = "12px system-ui, sans-serif";
		context.fillText(String(markers.length), width - 44, 47);
		context.fillText("invalid", width - 72, height - 18);
		context.restore();
	}

	function drawSummary(context, summary, x, y) {
		context.save();
		context.fillStyle = "#26313f";
		context.font = "12px system-ui, sans-serif";
		const text = [
			`Gross ${formatWeight(summary.total_gross_weight_kg)}`,
			`Scrap ${formatWeight(summary.total_scrap_weight_kg)}`,
			`FG est. ${formatWeight(summary.derived_fg_estimate_kg)}`,
		].join("   ");
		context.fillText(text, x, y);
		context.restore();
	}

	function formatWeight(value) {
		const number = numberOrNull(value) || 0;
		return `${number.toFixed(3)} kg`;
	}

	function formatDimension(value) {
		const number = numberOrNull(value) || 0;
		return Number.isInteger(number) ? String(number) : number.toFixed(1);
	}

	window.SheetLayoutCanvas = {
		buildPayloadFromDoc,
		debounce,
		render,
	};
})();
