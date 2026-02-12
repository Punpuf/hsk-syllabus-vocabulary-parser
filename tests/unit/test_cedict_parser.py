"""Unit tests for CC-CEDICT parsing behavior."""

from __future__ import annotations

from hsk_pipeline.cedict.parser import parse_cedict_lines


def test_parse_cedict_lines_preserves_slash_delimited_glosses() -> None:
    entries = parse_cedict_lines(
        iter(["籃 篮 [lan2] /basket (receptacle)/basket (in basketball)/\n"])
    )

    # Both simp/trad records are emitted; each keeps slash-delimited glosses.
    assert len(entries) == 2
    assert {entry.word for entry in entries} == {"籃", "篮"}
    assert {entry.definition for entry in entries} == {"basket (receptacle)/basket (in basketball)"}
