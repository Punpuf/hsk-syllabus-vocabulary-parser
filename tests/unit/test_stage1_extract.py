"""Unit tests for Stage 1 row extraction and parsing helpers."""

from __future__ import annotations

from hsk_pipeline.models import RawRow
from hsk_pipeline.stages.stage1_extract import parse_entries, parse_levels, split_pos_groups


def test_parse_levels_expands_parenthesized_levels() -> None:
    """The parser should expand extra levels enclosed in full-width parentheses."""

    assert parse_levels("1") == ["1"]
    assert parse_levels("1（4）") == ["1", "4"]
    assert parse_levels("3（4）（7-9）") == ["3", "4", "7-9"]


def test_split_pos_groups_preserves_parenthesized_bundle() -> None:
    """The base POS group should stay separate from parenthesized extra-level groups."""

    assert split_pos_groups("形、介、（动、量）") == ["形、介", "动、量"]


def test_parse_entries_expands_multilevel_rows() -> None:
    """One source line with multiple levels should yield aligned output rows."""

    lines = [
        "序号 等级 词语 拼音 词性",
        "7 1（4） 半 bàn 数、（副）",
    ]

    rows = parse_entries(lines)

    assert rows == [
        RawRow("7", "1", "半", "bàn", "数"),
        RawRow("7", "4", "半", "bàn", "副"),
    ]


def test_parse_entries_handles_pending_hanzi_line() -> None:
    """When Hanzi is delayed to the next line, the parser should stitch rows correctly."""

    lines = [
        "100 3 dǎdiànhuà 动",
        "打电话",
    ]

    rows = parse_entries(lines)

    assert rows == [
        RawRow("100", "3", "打电话", "dǎdiànhuà", "动"),
    ]
