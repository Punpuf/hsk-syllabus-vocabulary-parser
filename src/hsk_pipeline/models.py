"""Data models used across extraction pipeline stages.

This module defines explicit immutable row contracts between stages so each stage
has a narrow, testable interface and downstream code can rely on stable fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RawRow:
    """Stage 1 row extracted from the PDF before any pinyin enrichment.

    The row stores exactly the fields available in the syllabus word table after
    level/POS splitting has been applied.
    """

    word_index: str
    level: str
    word: str
    pinyin: str
    part_of_speech: str


@dataclass(frozen=True)
class NumberedRow:
    """Stage 2 row with source pinyin converted to numbered pinyin syllables.

    This stage preserves all Stage 1 data and adds ``pinyin_numbered`` generated
    from the source pinyin while aligning syllable boundaries to Hanzi.
    """

    word_index: str
    level: str
    word: str
    pinyin: str
    part_of_speech: str
    pinyin_numbered: str


@dataclass(frozen=True)
class EnrichedRow:
    """Stage 3 row enriched with CC-CEDICT pronunciation and definition.

    The final output contract includes normalized CC-CEDICT pinyin, the selected
    traditional form(s), and a selected CC-CEDICT definition alongside the
    source-derived and numbered fields.
    """

    word_index: str
    level: str
    word: str
    pinyin: str
    part_of_speech: str
    pinyin_numbered: str
    pinyin_cc_cedict: str
    traditional_cc_cedict: str
    definition_cc_cedict: str


@dataclass(frozen=True)
class ToneInsensitiveUniqueMatch:
    """Report item for tone-insensitive resolution with exactly one candidate."""

    word_index: str
    word: str
    source_pinyin: str
    source_pinyin_numbered: str
    selected_cedict_pinyin: str


@dataclass(frozen=True)
class ToneInsensitiveMultiMatch:
    """Report item for tone-insensitive resolution requiring disambiguation."""

    word_index: str
    word: str
    source_pinyin: str
    source_pinyin_numbered: str
    candidate_cedict_pinyin: tuple[str, ...]
    selected_cedict_pinyin: str


@dataclass(frozen=True)
class PatchedMatch:
    """Report item for rows resolved by patch CC-CEDICT entries."""

    word_index: str
    word: str
    source_pinyin_numbered: str
    selected_cedict_pinyin: str


@dataclass(frozen=True)
class NoMatchItem:
    """Report item for unresolved rows after all resolution strategies."""

    word_index: str
    word: str
    source_pinyin: str
    source_pinyin_numbered: str
    notes: str


@dataclass(frozen=True)
class ResolutionReport:
    """Stage 3 resolution diagnostics captured for reporting.

    The report tracks rows that were not resolved by exact matching and which
    fallback branch was used. Lists are kept as ordered append-only sequences
    during processing and sorted later by report builders for deterministic output.
    """

    tone_insensitive_unique: tuple[ToneInsensitiveUniqueMatch, ...] = field(default_factory=tuple)
    tone_insensitive_multi: tuple[ToneInsensitiveMultiMatch, ...] = field(default_factory=tuple)
    patched: tuple[PatchedMatch, ...] = field(default_factory=tuple)
    no_match: tuple[NoMatchItem, ...] = field(default_factory=tuple)
