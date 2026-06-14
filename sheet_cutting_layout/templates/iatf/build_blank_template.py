"""Generate the shipped blank FRM/PRD/15 IATF export template.

This produces a minimally-correct blank workbook so the exporter is
testable end to end. It is not the audit-approved page.
"""

from __future__ import annotations

import os

from openpyxl import Workbook

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "sheet_cutting_layout.xlsx")

STATIC_LABELS = {
	"A1": "Company:",
	"A2": "Doc No:",
	"B2": "FRM/PRD/15",
	"A5": "Part Name:",
	"M5": "Part Number:",
	"A6": "Project:",
	"A8": "Sheet Thickness (mm):",
	"A9": "Sheet T/W/L (mm):",
	"A10": "Strip Weight (kg):",
	"A11": "Strip T/W/L (mm):",
	"A12": "Parts / Strip:",
	"A13": "No. of Strips:",
	"A14": "Parts / Sheet:",
	"A15": "Gross Wt / Part (kg):",
	"A16": "Net Wt / Part (kg):",
	"A17": "Scrap Wt / Part (kg):",
	"O7": "Item",
	"P7": "Gross",
	"Q7": "F.G.",
	"R7": "Scrap",
	"S7": "Nos",
	"T7": "Total Wt",
	"U7": "RM Wt",
	"A38": "Prepared By (Engg/Prod):",
	"G38": "Checked by Production Manager:",
	"M38": "BOM Updated by Purchase:",
	"R38": "Released by Management Rep:",
}


def build_blank_template() -> None:
	workbook = Workbook()
	worksheet = workbook.active
	worksheet.title = "FRM-PRD-15"
	for coordinate, label in STATIC_LABELS.items():
		worksheet[coordinate] = label
	workbook.save(TEMPLATE_PATH)


if __name__ == "__main__":
	build_blank_template()
	print(f"Wrote {TEMPLATE_PATH}")
