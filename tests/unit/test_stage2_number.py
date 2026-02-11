"""Unit tests for Stage 2 pinyin numbering behavior."""

from __future__ import annotations

from pathlib import Path

from hsk_pipeline.cedict.repository import CedictRepository
from hsk_pipeline.models import RawRow
from hsk_pipeline.stages.stage2_number import add_pinyin_numbered


def test_add_pinyin_numbered_basic_and_slashed_variants() -> None:
    """Stage 2 should generate numbered pinyin with preserved slash variants."""

    repo = CedictRepository(Path("tests/fixtures/mini_cedict.u8"))
    rows = [
        RawRow("1", "1", "爱", "ài", "动"),
        RawRow("3", "1", "爸爸", "bàba", "名"),
        RawRow("4", "1", "谁", "shéi/shuí", "代"),
        RawRow("5", "1", "一个", "yíge", "数"),
    ]

    out = add_pinyin_numbered(rows, cedict_repo=repo)

    assert [row.pinyin_numbered for row in out] == [
        "ai4",
        "ba4 ba5",
        "shei2/shui2",
        "yi2 ge5",
    ]
