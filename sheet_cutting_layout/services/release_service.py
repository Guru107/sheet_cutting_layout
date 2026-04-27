from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

LayoutReleaseStatus = Literal["Approved by Purchase", "Release Pending Impact", "Released"]
ImpactReferenceDoctype = Literal["Work Order", "Production Plan"]
ImpactDecision = Literal["Use Old BOM", "Use New BOM", "Cancel Reference"]
ImpactStatus = Literal["Open", "Resolved"]

IMPACT_REFERENCE_DOCTYPES: frozenset[str] = frozenset({"Work Order", "Production Plan"})


class ManufacturingDocument(Protocol):
	doctype: str
	name: str
	bom_no: str
	status: str


class ReleaseLayoutDocument(Protocol):
	bom_replacements: Mapping[str, str]
	status: LayoutReleaseStatus
	impact_resolutions: list[LayoutImpactResolution]


@dataclass
class LayoutImpactResolution:
	reference_doctype: ImpactReferenceDoctype
	reference_docname: str
	old_bom: str
	new_bom: str
	decision: ImpactDecision | None = None
	decided_by: str | None = None
	decided_on: datetime | None = None
	status: ImpactStatus = "Open"


@dataclass
class ReleaseResult:
	status: LayoutReleaseStatus
	impact_rows: list[LayoutImpactResolution] = field(default_factory=list)


def release_layout(
	layout: ReleaseLayoutDocument,
	*,
	open_documents: Sequence[ManufacturingDocument],
	bom_replacements: Mapping[str, str] | None = None,
) -> ReleaseResult:
	replacements = bom_replacements if bom_replacements is not None else layout.bom_replacements
	impact_rows = [
		LayoutImpactResolution(
			reference_doctype=_impact_doctype(document.doctype),
			reference_docname=document.name,
			old_bom=document.bom_no,
			new_bom=replacements[document.bom_no],
		)
		for document in open_documents
		if _is_impacted_open_document(document, replacements)
	]
	layout.impact_resolutions = impact_rows

	if impact_rows:
		layout.status = "Release Pending Impact"
	else:
		layout.status = "Released"

	return ReleaseResult(status=layout.status, impact_rows=list(impact_rows))


def resolve_impact(
	impact_row: LayoutImpactResolution,
	*,
	decision: ImpactDecision,
	decided_by: str,
	decided_on: datetime,
) -> LayoutImpactResolution:
	impact_row.decision = decision
	impact_row.decided_by = decided_by
	impact_row.decided_on = decided_on
	impact_row.status = "Resolved"
	return impact_row


def finalize_release(layout: ReleaseLayoutDocument) -> ReleaseResult:
	for impact_row in layout.impact_resolutions:
		impact_row.status = "Resolved" if _has_complete_decision(impact_row) else "Open"

	if all(_has_complete_decision(impact_row) for impact_row in layout.impact_resolutions):
		layout.status = "Released"
	else:
		layout.status = "Release Pending Impact"

	return ReleaseResult(status=layout.status, impact_rows=list(layout.impact_resolutions))


def _is_impacted_open_document(document: ManufacturingDocument, replacements: Mapping[str, str]) -> bool:
	return (
		document.doctype in IMPACT_REFERENCE_DOCTYPES
		and document.status == "Open"
		and document.bom_no in replacements
	)


def _impact_doctype(doctype: str) -> ImpactReferenceDoctype:
	if doctype == "Work Order":
		return "Work Order"
	if doctype == "Production Plan":
		return "Production Plan"
	raise ValueError(f"Unsupported impact reference doctype: {doctype}")


def _has_complete_decision(impact_row: LayoutImpactResolution) -> bool:
	return bool(impact_row.decision and impact_row.decided_by and impact_row.decided_on)
