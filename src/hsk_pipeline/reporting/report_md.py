"""Markdown report generation for extraction run summaries."""

from __future__ import annotations

import re
from typing import Iterable, Sequence

from hsk_pipeline.models import EnrichedRow, ResolutionReport
from hsk_pipeline.validation import collect_level_counts, collect_pos_counts


def _level_sort_key(level: str) -> tuple[int, str]:
    """Sort level labels by leading numeric prefix then raw label.

    Args:
        level: HSK level label such as ``1`` or ``7-9``.

    Returns:
        Tuple suitable for stable sorting.
    """

    match = re.match(r"^(\d+)", level)
    leading = int(match.group(1)) if match else 10**9
    return leading, level


def _markdown_table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    """Render a deterministic GitHub-flavored markdown table.

    Args:
        headers: Table header labels.
        rows: Table body rows as string sequences.

    Returns:
        Markdown table text.
    """

    line_header = "| " + " | ".join(headers) + " |"
    line_sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([line_header, line_sep, *body])


def build_report_md(rows: list[EnrichedRow], report: ResolutionReport) -> str:
    """Build the extraction markdown report for one pipeline run.

    Args:
        rows: Final enriched rows.
        report: Stage 3 resolution report details.

    Returns:
        Full markdown content with summary tables.
    """

    level_counts = collect_level_counts(rows)
    level_rows = [
        (level, str(level_counts[level])) for level in sorted(level_counts, key=_level_sort_key)
    ]

    pos_counts = collect_pos_counts(rows)
    pos_rows = [
        (token, str(pos_counts[token]))
        for token in sorted(pos_counts, key=lambda item: (-pos_counts[item], item))
    ]

    tone_unique_rows = [
        (
            item.word_index,
            item.word,
            item.source_pinyin_numbered,
            item.selected_cedict_pinyin,
        )
        for item in sorted(
            report.tone_insensitive_unique,
            key=lambda item: (int(item.word_index), item.word, item.source_pinyin_numbered),
        )
    ]

    tone_multi_rows = [
        (
            item.word_index,
            item.word,
            item.source_pinyin_numbered,
            ", ".join(item.candidate_cedict_pinyin),
            item.selected_cedict_pinyin,
        )
        for item in sorted(
            report.tone_insensitive_multi,
            key=lambda item: (int(item.word_index), item.word, item.source_pinyin_numbered),
        )
    ]

    patched_rows = [
        (
            item.word_index,
            item.word,
            item.source_pinyin_numbered,
            item.selected_cedict_pinyin,
        )
        for item in sorted(
            report.patched,
            key=lambda item: (int(item.word_index), item.word, item.source_pinyin_numbered),
        )
    ]

    no_match_rows = [
        (
            item.word_index,
            item.word,
            item.source_pinyin_numbered,
            item.notes,
        )
        for item in sorted(
            report.no_match,
            key=lambda item: (int(item.word_index), item.word, item.source_pinyin_numbered),
        )
    ]

    sections = [
        "# Extraction Report",
        "",
        "## Words per HSK level",
        _markdown_table(["level", "word_count"], level_rows),
        "",
        "## Part-of-Speech Tokens Present",
        _markdown_table(["part_of_speech", "count"], pos_rows),
        "",
        "## Tone-insensitive unique matches",
        _markdown_table(
            ["word_index", "word", "source_pinyin_numbered", "selected_cedict_pinyin"],
            tone_unique_rows,
        ),
        "",
        "## Tone-insensitive match with multiple candidates",
        _markdown_table(
            [
                "word_index",
                "word",
                "source_pinyin_numbered",
                "candidate_cedict_pinyin",
                "selected_cedict_pinyin",
            ],
            tone_multi_rows,
        ),
        "",
        "## Patched with CC-CEDICT patch file",
        _markdown_table(
            ["word_index", "word", "source_pinyin_numbered", "selected_cedict_pinyin"],
            patched_rows,
        ),
        "",
        "## No match with CC-CEDICT",
        _markdown_table(["word_index", "word", "source_pinyin_numbered", "notes"], no_match_rows),
    ]

    return "\n".join(sections) + "\n"
