"""Top-level orchestration for staged HSK extraction pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hsk_pipeline.cedict.disambiguation import DisambiguationRepository
from hsk_pipeline.cedict.repository import CedictRepository
from hsk_pipeline.models import EnrichedRow, ResolutionReport
from hsk_pipeline.stages.stage1_extract import extract_raw_rows
from hsk_pipeline.stages.stage2_number import add_pinyin_numbered
from hsk_pipeline.stages.stage3_enrich import enrich_with_cedict
from hsk_pipeline.validation import (
    missing_word_indexes,
    validate_enriched_rows,
    validate_numbered_rows,
    validate_raw_rows,
)


@dataclass(frozen=True)
class PipelineResult:
    """Result bundle returned by :func:`run_pipeline`.

    Attributes:
        rows: Final enriched rows.
        report: Stage 3 resolution report details.
        missing_indexes: Missing integer word indexes across output range.
    """

    rows: tuple[EnrichedRow, ...]
    report: ResolutionReport
    missing_indexes: tuple[int, ...]


def run_pipeline(
    pdf_path: Path,
    page_start: int,
    page_end: int | None,
    cedict_path: Path,
    disambiguation_path: Path,
    patch_path: Path,
    allow_unresolved: bool = False,
) -> PipelineResult:
    """Execute all pipeline stages from PDF extraction to enrichment.

    Args:
        pdf_path: Source syllabus PDF path.
        page_start: 1-based inclusive start page.
        page_end: 1-based inclusive end page or ``None``.
        cedict_path: Main CC-CEDICT file path.
        disambiguation_path: Disambiguation TSV path.
        patch_path: Patch CEDICT path.
        allow_unresolved: Whether unresolved enrichment rows are allowed.

    Returns:
        ``PipelineResult`` containing rows, report, and continuity diagnostics.
    """

    raw_rows = extract_raw_rows(pdf_path=pdf_path, page_start=page_start, page_end=page_end)
    validate_raw_rows(raw_rows)

    cedict_repo = CedictRepository(cedict_path)
    numbered_rows = add_pinyin_numbered(raw_rows, cedict_repo=cedict_repo)
    validate_numbered_rows(numbered_rows)

    disambiguation_repo = DisambiguationRepository(disambiguation_path)
    patch_repo = CedictRepository(patch_path)
    enriched_rows, resolution_report = enrich_with_cedict(
        rows=numbered_rows,
        cedict_repo=cedict_repo,
        disambiguation_repo=disambiguation_repo,
        patch_repo=patch_repo,
        allow_unresolved=allow_unresolved,
    )
    validate_enriched_rows(enriched_rows, allow_unresolved=allow_unresolved)

    return PipelineResult(
        rows=tuple(enriched_rows),
        report=resolution_report,
        missing_indexes=tuple(missing_word_indexes(enriched_rows)),
    )
