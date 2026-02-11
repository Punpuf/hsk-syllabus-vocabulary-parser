"""Validation helpers for stage outputs and final dataset integrity."""

from __future__ import annotations

from collections import Counter
import re
from typing import Sequence

from hsk_pipeline.models import EnrichedRow, NumberedRow, RawRow

VALID_HSK_LEVELS = {"1", "2", "3", "4", "5", "6", "7-9"}
WORD_VALID_RE = re.compile(r"^[一-鿿]+[12]?$")
PINYIN_NUMBERED_TOKEN_RE = re.compile(r"^[a-zü]+[1-5]$")


def validate_raw_rows(rows: Sequence[RawRow]) -> None:
    """Validate Stage 1 rows for required field and schema constraints.

    Args:
        rows: Stage 1 rows to validate.

    Raises:
        ValueError: If any row violates the expected shape.
    """

    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        if not row.word_index.isdigit():
            errors.append(f"Row {idx}: invalid word_index '{row.word_index}'")
        if row.level not in VALID_HSK_LEVELS:
            errors.append(f"Row {idx}: invalid level '{row.level}'")
        if not WORD_VALID_RE.fullmatch(row.word):
            errors.append(f"Row {idx}: invalid word '{row.word}'")
        if not row.pinyin.strip():
            errors.append(f"Row {idx}: empty pinyin")

    if errors:
        preview = "\n".join(f"- {item}" for item in errors[:25])
        rest = len(errors) - min(25, len(errors))
        more = f"\n- ... and {rest} more" if rest > 0 else ""
        raise ValueError(f"Stage 1 validation failed with {len(errors)} errors:\n{preview}{more}")


def validate_numbered_rows(rows: Sequence[NumberedRow]) -> None:
    """Validate Stage 2 rows and numbered pinyin token formatting.

    Args:
        rows: Stage 2 rows to validate.

    Raises:
        ValueError: If ``pinyin_numbered`` tokens are malformed.
    """

    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        if not row.pinyin_numbered.strip():
            errors.append(f"Row {idx}: empty pinyin_numbered")
            continue
        for variant in row.pinyin_numbered.split("/"):
            tokens = [token for token in variant.strip().split() if token]
            if not tokens:
                errors.append(f"Row {idx}: empty pinyin variant in '{row.pinyin_numbered}'")
                continue
            for token in tokens:
                if not PINYIN_NUMBERED_TOKEN_RE.fullmatch(token):
                    errors.append(
                        f"Row {idx}: invalid pinyin_numbered token '{token}' in '{row.pinyin_numbered}'"
                    )

    if errors:
        preview = "\n".join(f"- {item}" for item in errors[:25])
        rest = len(errors) - min(25, len(errors))
        more = f"\n- ... and {rest} more" if rest > 0 else ""
        raise ValueError(f"Stage 2 validation failed with {len(errors)} errors:\n{preview}{more}")


def validate_enriched_rows(rows: Sequence[EnrichedRow], allow_unresolved: bool = False) -> None:
    """Validate Stage 3 rows including enrichment-required fields.

    Args:
        rows: Stage 3 rows to validate.
        allow_unresolved: Whether empty enrichment fields are allowed.

    Raises:
        ValueError: If required fields are missing.
    """

    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        if not row.pinyin_cc_cedict and not allow_unresolved:
            errors.append(f"Row {idx}: empty pinyin_cc-cedict")
        if not row.definition_cc_cedict and not allow_unresolved:
            errors.append(f"Row {idx}: empty definition_cc-cedict")

    if errors:
        preview = "\n".join(f"- {item}" for item in errors[:25])
        rest = len(errors) - min(25, len(errors))
        more = f"\n- ... and {rest} more" if rest > 0 else ""
        raise ValueError(f"Stage 3 validation failed with {len(errors)} errors:\n{preview}{more}")


def missing_word_indexes(rows: Sequence[RawRow | NumberedRow | EnrichedRow]) -> list[int]:
    """Compute missing numeric word indexes in the observed index range.

    Args:
        rows: Any row type containing ``word_index``.

    Returns:
        Missing integer indexes between min/max observed values.
    """

    if not rows:
        return []

    indexes = sorted({int(row.word_index) for row in rows})
    start = indexes[0]
    end = indexes[-1]
    observed = set(indexes)
    return [idx for idx in range(start, end + 1) if idx not in observed]


def collect_level_counts(rows: Sequence[RawRow | NumberedRow | EnrichedRow]) -> dict[str, int]:
    """Count rows by HSK level.

    Args:
        rows: Any row type containing ``level``.

    Returns:
        Dictionary of level label to row count.
    """

    counter: Counter[str] = Counter()
    for row in rows:
        counter[row.level] += 1
    return dict(counter)


def collect_pos_counts(rows: Sequence[RawRow | NumberedRow | EnrichedRow]) -> dict[str, int]:
    """Count each POS token split by the Chinese delimiter ``、``.

    Args:
        rows: Any row type containing ``part_of_speech``.

    Returns:
        Dictionary of POS token to count.
    """

    counter: Counter[str] = Counter()
    for row in rows:
        if not row.part_of_speech.strip():
            continue
        for token in row.part_of_speech.split("、"):
            token = token.strip()
            if token:
                counter[token] += 1
    return dict(counter)
