"""Unit tests for TSV serialization helpers."""

from __future__ import annotations

from pathlib import Path

from hsk_pipeline.io.tsv_io import TSV_HEADER, write_tsv
from hsk_pipeline.models import EnrichedRow


def test_write_tsv_includes_traditional_column_between_pinyin_and_definition(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out.tsv"
    row = EnrichedRow(
        word_index="1",
        level="1",
        word="爱",
        pinyin="ài",
        part_of_speech="动",
        pinyin_numbered="ai4",
        pinyin_cc_cedict="ai4",
        traditional_cc_cedict="愛",
        definition_cc_cedict="to love",
    )

    write_tsv([row], output_path=output, include_header=True)
    lines = output.read_text(encoding="utf-8").splitlines()

    assert TSV_HEADER == [
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
    assert lines[0].split("\t") == TSV_HEADER
    assert lines[1].split("\t") == ["1", "1", "爱", "ài", "动", "ai4", "ai4", "愛", "to love"]
