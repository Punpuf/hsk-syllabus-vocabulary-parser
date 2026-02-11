"""CLI entrypoint for modular HSK extraction pipeline."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Sequence

from hsk_pipeline.io.tsv_io import write_tsv
from hsk_pipeline.pipeline import run_pipeline
from hsk_pipeline.reporting.report_md import build_report_md
from hsk_pipeline.validation import collect_level_counts, collect_pos_counts


def _resolve_default_cedict_path() -> Path:
    """Resolve default CC-CEDICT path from project layout.

    Returns:
        Preferred dictionary path, favoring ``data/cedict_ts.u8`` when present
        and falling back to project-root ``cedict_ts.u8``.
    """

    cwd_data = Path("data") / "cedict_ts.u8"
    if cwd_data.exists():
        return cwd_data
    return Path("cedict_ts.u8")


def _format_integer_ranges(values: Sequence[int]) -> str:
    """Format sorted integers as compact ranges like ``3-5, 8, 10-12``.

    Args:
        values: Sorted integer list.

    Returns:
        Compact range string.
    """

    if not values:
        return ""

    ranges: list[str] = []
    start = values[0]
    prev = values[0]

    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = value
        prev = value

    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(ranges)


def _format_table(headers: Sequence[str], data_rows: Sequence[Sequence[str]]) -> str:
    """Format rows as an ASCII table for terminal output.

    Args:
        headers: Table headers.
        data_rows: Row values.

    Returns:
        Monospace table string.
    """

    widths = [len(header) for header in headers]
    for row in data_rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    header_line = " | ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers))
    separator_line = "-+-".join("-" * width for width in widths)
    body_lines = [
        " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(row)) for row in data_rows
    ]
    return "\n".join([header_line, separator_line, *body_lines])


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured parser for extraction command.
    """

    parser = argparse.ArgumentParser(description="Extract HSK word list from PDF into TSV.")
    parser.add_argument("--pdf", required=True, type=Path, help="Path to source syllabus PDF.")
    parser.add_argument("--output", required=True, type=Path, help="Destination TSV output path.")
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Markdown report output path (default: report.md next to TSV).",
    )
    parser.add_argument("--page-start", type=int, default=1, help="1-based start page (inclusive).")
    parser.add_argument("--page-end", type=int, default=None, help="1-based end page (inclusive).")
    parser.add_argument(
        "--cedict",
        type=Path,
        default=_resolve_default_cedict_path(),
        help="Path to CC-CEDICT .u8 file.",
    )
    parser.add_argument(
        "--disambiguation",
        type=Path,
        default=Path("data") / "disambiguation.tsv",
        help="Path to disambiguation TSV.",
    )
    parser.add_argument(
        "--patch",
        type=Path,
        default=Path("data") / "cedict_patch.u8",
        help="Path to CC-CEDICT patch .u8 file.",
    )
    parser.add_argument(
        "--allow-unresolved",
        action="store_true",
        help="Allow unresolved CC-CEDICT rows instead of failing.",
    )
    parser.add_argument("--no-header", action="store_true", help="Do not write TSV header.")
    return parser


def _print_output_analysis(rows, missing_indexes: Sequence[int]) -> None:
    """Print continuity and summary tables for extracted output.

    Args:
        rows: Enriched rows.
        missing_indexes: Missing numeric indexes computed by pipeline.
    """

    if not rows:
        print("No rows parsed; skipping output analysis.")
        return

    indexes = sorted({int(row.word_index) for row in rows})
    if missing_indexes:
        print(
            "WARNING: Missing word_index values "
            f"({len(missing_indexes)}): {_format_integer_ranges(missing_indexes)}"
        )
    else:
        print(
            "word_index continuity check: no missing values " f"(range {indexes[0]}-{indexes[-1]})."
        )

    pos_counts = collect_pos_counts(rows)
    pos_rows = [
        [token, str(count)]
        for token, count in sorted(pos_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    print("\nPart-of-speech tokens in output TSV:")
    print(_format_table(["part_of_speech", "count"], pos_rows))

    level_counts = collect_level_counts(rows)
    level_rows = [
        [level, str(level_counts[level])]
        for level in sorted(level_counts, key=lambda v: (int(v.split("-")[0]), v))
    ]
    print("\nWord rows by HSK level:")
    print(_format_table(["level", "word_count"], level_rows))


def main() -> int:
    """Run CLI workflow from arguments through artifact generation.

    Returns:
        Zero exit status on success.
    """

    parser = build_arg_parser()
    args = parser.parse_args()

    if not args.pdf.exists():
        raise SystemExit(f"PDF not found: {args.pdf}")

    report_path = args.report if args.report is not None else args.output.parent / "report.md"

    result = run_pipeline(
        pdf_path=args.pdf,
        page_start=args.page_start,
        page_end=args.page_end,
        cedict_path=args.cedict,
        disambiguation_path=args.disambiguation,
        patch_path=args.patch,
        allow_unresolved=args.allow_unresolved,
    )

    write_tsv(result.rows, output_path=args.output, include_header=not args.no_header)
    report_md = build_report_md(list(result.rows), result.report)
    report_path.write_text(report_md, encoding="utf-8")

    print(f"Wrote {len(result.rows)} rows to {args.output}")
    print(f"Wrote report to {report_path}")
    _print_output_analysis(result.rows, result.missing_indexes)
    print(
        "\nResolution summary: "
        f"tone_insensitive_unique={len(result.report.tone_insensitive_unique)}, "
        f"tone_insensitive_multi={len(result.report.tone_insensitive_multi)}, "
        f"patched={len(result.report.patched)}, "
        f"no_match={len(result.report.no_match)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
