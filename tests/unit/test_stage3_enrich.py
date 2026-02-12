"""Unit tests for Stage 3 CC-CEDICT enrichment branches."""

from __future__ import annotations

from pathlib import Path

import pytest

from hsk_pipeline.cedict.disambiguation import DisambiguationRepository
from hsk_pipeline.cedict.repository import CedictRepository
from hsk_pipeline.models import NumberedRow
from hsk_pipeline.stages.stage3_enrich import enrich_with_cedict


def _write(path: Path, text: str) -> Path:
    """Write helper for fixture files in tmp directories."""

    path.write_text(text, encoding="utf-8")
    return path


def test_stage3_resolves_exact_unique_multi_patch_and_no_match(tmp_path: Path) -> None:
    """Stage 3 should exercise all resolution branches deterministically."""

    main_cedict = _write(
        tmp_path / "main.u8",
        "\n".join(
            [
                "# main",
                "行 行 [xing2] /to walk/",
                "行 行 [hang2] /row; line/",
                "一 一 [yi1] /one/",
                "一 一 [yi2] /one (sandhi)/",
                "一個 一个 [yi1 ge4] /one item/",
                "裡 里 [li3] /inside/",
                "裏 里 [li3] /interior/",
                "點 点 [dian3] /dot; point/",
            ]
        )
        + "\n",
    )
    patch_cedict = _write(
        tmp_path / "patch.u8",
        "\n".join(
            [
                "# patch",
                "龘 龘 [da2] /test patch entry/",
            ]
        )
        + "\n",
    )
    disambiguation = _write(
        tmp_path / "disambiguation.tsv",
        "word\tsource_pinyin_numbered\tselected_cedict_pinyin\n" "一\tyi4\tyi1\n",
    )

    rows = [
        NumberedRow("1", "1", "行", "xíng", "动", "xing2"),
        NumberedRow("2", "1", "一个", "yíge", "数", "yi2 ge4"),
        NumberedRow("3", "1", "一", "yì", "数", "yi4"),
        NumberedRow("4", "1", "龘", "dá", "名", "da2"),
        NumberedRow("5", "1", "龘龘", "dádá", "名", "da2 da2"),
        NumberedRow("6", "1", "点1", "diǎn", "名", "dian3"),
        NumberedRow("7", "1", "里", "lǐ", "名", "li3"),
    ]

    enriched, report = enrich_with_cedict(
        rows=rows,
        cedict_repo=CedictRepository(main_cedict),
        disambiguation_repo=DisambiguationRepository(disambiguation),
        patch_repo=CedictRepository(patch_cedict),
        allow_unresolved=True,
    )

    assert enriched[0].pinyin_cc_cedict == "xing2"
    assert enriched[1].pinyin_cc_cedict == "yi1 ge4"
    assert enriched[2].pinyin_cc_cedict == "yi1"
    assert enriched[3].pinyin_cc_cedict == "da2"
    assert enriched[4].pinyin_cc_cedict == ""
    assert enriched[5].pinyin_cc_cedict == "dian3"
    assert enriched[6].pinyin_cc_cedict == "li3"
    assert enriched[6].definition_cc_cedict == "inside/interior"
    assert "|" not in enriched[6].definition_cc_cedict

    assert enriched[0].traditional_cc_cedict == "行"
    assert enriched[1].traditional_cc_cedict == "一個"
    assert enriched[2].traditional_cc_cedict == "一"
    assert enriched[3].traditional_cc_cedict == "龘"
    assert enriched[4].traditional_cc_cedict == ""
    assert enriched[5].traditional_cc_cedict == "點"
    assert enriched[6].traditional_cc_cedict == "裏/裡"

    assert len(report.tone_insensitive_unique) == 1
    assert len(report.tone_insensitive_multi) == 1
    assert len(report.patched) == 1
    assert len(report.no_match) == 1


def test_stage3_fails_by_default_when_no_match_exists(tmp_path: Path) -> None:
    """Without allow_unresolved, unresolved rows should raise a hard error."""

    main_cedict = _write(tmp_path / "main.u8", "一 一 [yi1] /one/\n")
    patch_cedict = _write(tmp_path / "patch.u8", "# empty\n")
    disambiguation = _write(
        tmp_path / "disambiguation.tsv",
        "word\tsource_pinyin_numbered\tselected_cedict_pinyin\n",
    )

    rows = [NumberedRow("1", "1", "龘", "dá", "名", "da2")]

    with pytest.raises(ValueError):
        enrich_with_cedict(
            rows=rows,
            cedict_repo=CedictRepository(main_cedict),
            disambiguation_repo=DisambiguationRepository(disambiguation),
            patch_repo=CedictRepository(patch_cedict),
            allow_unresolved=False,
        )
