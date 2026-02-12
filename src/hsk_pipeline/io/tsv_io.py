"""TSV read/write helpers for pipeline output artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from hsk_pipeline.models import EnrichedRow

TSV_HEADER = [
    "word_index",
    "level",
    "word",
    "pinyin",
    "part_of_speech",
    "pinyin_numbered",
    "pinyin_cc-cedict",
    "traditional_cc-cedict",
    "definition_cc-cedict",
]


def write_tsv(rows: Sequence[EnrichedRow], output_path: Path, include_header: bool = True) -> None:
    """Write enriched rows to a TSV file using the canonical column order.

    Args:
        rows: Final enriched rows to serialize.
        output_path: Destination TSV file path.
        include_header: Whether to include a header row.
    """

    with output_path.open("w", encoding="utf-8") as handle:
        if include_header:
            handle.write("\t".join(TSV_HEADER))
            handle.write("\n")
        for row in rows:
            handle.write(
                "\t".join(
                    [
                        row.word_index,
                        row.level,
                        row.word,
                        row.pinyin,
                        row.part_of_speech,
                        row.pinyin_numbered,
                        row.pinyin_cc_cedict,
                        row.traditional_cc_cedict,
                        row.definition_cc_cedict,
                    ]
                )
            )
            handle.write("\n")
