from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

try:
	import frappe
except ImportError:

	class _ValidationError(Exception):
		pass

	class _FrappeCompat:
		ValidationError = _ValidationError

		@staticmethod
		def throw(message: str) -> None:
			raise _ValidationError(message)

	frappe = _FrappeCompat()


class FinishedPartRow(Protocol):
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float


class EndPieceRow(Protocol):
	end_piece_item: str | None
	weight_kg: float | None
	qty_per_sheet: float | None


class SheetCuttingLayoutDocument(Protocol):
	finished_parts: Sequence[FinishedPartRow]
	end_pieces: Sequence[EndPieceRow]
	process_scrap_item: str | None


ALNUM_RE = re.compile(r"^[A-Za-z0-9]+$")


def validate_finished_part_code(code: str) -> None:
	if not ALNUM_RE.fullmatch(code):
		frappe.throw("Finished part item code must be alphanumeric only")
	if not code.endswith("SHR"):
		frappe.throw("Finished part item code must end with SHR")


def validate_sheet_cutting_layout(layout: SheetCuttingLayoutDocument) -> None:
	finished_parts = list(getattr(layout, "finished_parts", []) or [])
	end_pieces = list(getattr(layout, "end_pieces", []) or [])

	if not finished_parts:
		frappe.throw("Sheet Cutting Layout requires at least one finished part")

	for finished_part in finished_parts:
		validate_finished_part_code(finished_part.finished_part_item)
		_validate_finished_part_weights(finished_part)
		if finished_part.scrap_weight_per_part_kg > 0 and _is_missing(
			getattr(layout, "process_scrap_item", None)
		):
			frappe.throw("Process scrap item is required when process scrap weight is positive")

	for end_piece in end_pieces:
		_validate_end_piece_required_fields(end_piece)

	if end_pieces:
		_validate_end_piece_distribution(finished_parts, end_pieces)


def _validate_finished_part_weights(finished_part: FinishedPartRow) -> None:
	if finished_part.gross_weight_per_part_kg < 0:
		frappe.throw("Gross weight per part must be non-negative")
	if finished_part.scrap_weight_per_part_kg < 0:
		frappe.throw("Scrap weight per part must be non-negative")


def _validate_end_piece_required_fields(end_piece: EndPieceRow) -> None:
	if _is_missing(end_piece.end_piece_item):
		frappe.throw("End piece item is required")
	if end_piece.weight_kg is None:
		frappe.throw("End piece weight is required")
	if end_piece.qty_per_sheet is None:
		frappe.throw("End piece quantity is required")


def _validate_end_piece_distribution(
	finished_parts: Sequence[FinishedPartRow],
	end_pieces: Sequence[EndPieceRow],
) -> None:
	for finished_part in finished_parts:
		if finished_part.parts_per_sheet <= 0:
			frappe.throw("Parts per sheet must be greater than zero for end-piece distribution")

		end_piece_weight_per_part = sum(
			(end_piece.weight_kg * end_piece.qty_per_sheet) / finished_part.parts_per_sheet
			for end_piece in end_pieces
			if end_piece.weight_kg is not None and end_piece.qty_per_sheet is not None
		)
		derived_fg_weight = (
			finished_part.gross_weight_per_part_kg
			- finished_part.scrap_weight_per_part_kg
			- end_piece_weight_per_part
		)
		if derived_fg_weight < 0:
			frappe.throw("Derived finished goods weight must be non-negative")


def _is_missing(value: object) -> bool:
	return value is None or (isinstance(value, str) and value.strip() == "")
