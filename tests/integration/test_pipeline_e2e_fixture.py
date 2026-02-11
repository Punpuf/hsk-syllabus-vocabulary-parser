"""Integration test chaining Stage 2 and Stage 3 on fixture data."""

from __future__ import annotations

from pathlib import Path

from hsk_pipeline.cedict.disambiguation import DisambiguationRepository
from hsk_pipeline.cedict.repository import CedictRepository
from hsk_pipeline.models import RawRow
from hsk_pipeline.stages.stage2_number import add_pinyin_numbered
from hsk_pipeline.stages.stage3_enrich import enrich_with_cedict
from hsk_pipeline.validation import (
    validate_enriched_rows,
    validate_numbered_rows,
    validate_raw_rows,
)


def test_stage_chain_fixture_roundtrip(tmp_path: Path) -> None:
    """Stage 2+3 integration should produce enriched rows without unresolved items."""

    main = tmp_path / "main.u8"
    main.write_text(
        "\n".join(
            [
                "愛 爱 [ai4] /to love/",
                "爸爸 爸爸 [ba4 ba5] /dad/",
                "一 一 [yi1] /one/",
                "一個 一个 [yi1 ge4] /one item/",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    patch = tmp_path / "patch.u8"
    patch.write_text("# empty\n", encoding="utf-8")
    disambiguation = tmp_path / "disambiguation.tsv"
    disambiguation.write_text(
        "word\tsource_pinyin_numbered\tselected_cedict_pinyin\n",
        encoding="utf-8",
    )

    raw_rows = [
        RawRow("1", "1", "爱", "ài", "动"),
        RawRow("2", "1", "爸爸", "bàba", "名"),
        RawRow("3", "1", "一个", "yíge", "数"),
    ]

    validate_raw_rows(raw_rows)
    numbered_rows = add_pinyin_numbered(raw_rows, CedictRepository(main))
    validate_numbered_rows(numbered_rows)

    enriched_rows, report = enrich_with_cedict(
        rows=numbered_rows,
        cedict_repo=CedictRepository(main),
        disambiguation_repo=DisambiguationRepository(disambiguation),
        patch_repo=CedictRepository(patch),
        allow_unresolved=False,
    )
    validate_enriched_rows(enriched_rows, allow_unresolved=False)

    assert len(enriched_rows) == 3
    assert len(report.no_match) == 0
    assert [row.pinyin_cc_cedict for row in enriched_rows] == ["ai4", "ba4 ba5", "yi1 ge4"]
