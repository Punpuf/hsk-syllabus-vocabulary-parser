"""Unit tests for markdown report generation."""

from __future__ import annotations

from hsk_pipeline.models import (
    EnrichedRow,
    NoMatchItem,
    PatchedMatch,
    ResolutionReport,
    ToneInsensitiveMultiMatch,
    ToneInsensitiveUniqueMatch,
)
from hsk_pipeline.reporting.report_md import build_report_md


def test_build_report_md_contains_required_sections() -> None:
    """Report output should include all required summary sections."""

    rows = [
        EnrichedRow("1", "1", "爱", "ài", "动", "ai4", "ai4", "to love"),
        EnrichedRow("2", "2", "半", "bàn", "名", "ban4", "ban4", "half"),
    ]
    report = ResolutionReport(
        tone_insensitive_unique=(ToneInsensitiveUniqueMatch("2", "半", "bàn", "ban4", "ban4"),),
        tone_insensitive_multi=(
            ToneInsensitiveMultiMatch("3", "一", "yì", "yi4", ("yi1", "yi2"), "yi1"),
        ),
        patched=(PatchedMatch("4", "龘", "da2", "da2"),),
        no_match=(NoMatchItem("5", "龘龘", "dádá", "da2 da2", "no_word_entry"),),
    )

    markdown = build_report_md(rows, report)

    assert "## Words per HSK level" in markdown
    assert "## Part-of-Speech Tokens Present" in markdown
    assert "## Tone-insensitive unique matches" in markdown
    assert "## Tone-insensitive match with multiple candidates" in markdown
    assert "## No match with CC-CEDICT" in markdown
    assert "| level | word_count |" in markdown
