"""Unit tests for Stage 3 enriched-row validation."""

from __future__ import annotations

import pytest

from hsk_pipeline.models import EnrichedRow
from hsk_pipeline.validation import validate_enriched_rows


def _row(
    *,
    pinyin_cc_cedict: str = "ai4",
    traditional_cc_cedict: str = "愛",
    definition_cc_cedict: str = "to love",
) -> EnrichedRow:
    return EnrichedRow(
        word_index="1",
        level="1",
        word="爱",
        pinyin="ài",
        part_of_speech="动",
        pinyin_numbered="ai4",
        pinyin_cc_cedict=pinyin_cc_cedict,
        traditional_cc_cedict=traditional_cc_cedict,
        definition_cc_cedict=definition_cc_cedict,
    )


def test_validate_enriched_rows_accepts_valid_traditional_single_and_multi() -> None:
    rows = [
        _row(traditional_cc_cedict="愛"),
        _row(traditional_cc_cedict="裏/裡"),
    ]

    validate_enriched_rows(rows, allow_unresolved=False)


def test_validate_enriched_rows_rejects_non_hanzi_traditional() -> None:
    with pytest.raises(ValueError, match="invalid traditional_cc-cedict"):
        validate_enriched_rows([_row(traditional_cc_cedict="A")], allow_unresolved=False)


def test_validate_enriched_rows_rejects_empty_segment() -> None:
    with pytest.raises(ValueError, match="invalid traditional_cc-cedict"):
        validate_enriched_rows([_row(traditional_cc_cedict="傳統//繁體")], allow_unresolved=False)


def test_validate_enriched_rows_allows_empty_enrichment_when_unresolved_enabled() -> None:
    validate_enriched_rows(
        [
            _row(
                pinyin_cc_cedict="",
                traditional_cc_cedict="",
                definition_cc_cedict="",
            )
        ],
        allow_unresolved=True,
    )


def test_validate_enriched_rows_requires_non_empty_traditional_when_unresolved_disallowed() -> None:
    with pytest.raises(ValueError, match="empty traditional_cc-cedict"):
        validate_enriched_rows(
            [
                _row(
                    pinyin_cc_cedict="ai4",
                    traditional_cc_cedict="",
                    definition_cc_cedict="to love",
                )
            ],
            allow_unresolved=False,
        )
