"""Matching helpers for selecting CC-CEDICT pronunciations."""

from __future__ import annotations

from dataclasses import dataclass

from hsk_pipeline.cedict.parser import CedictEntry


@dataclass(frozen=True)
class CandidateGroup:
    """Grouped CEDICT candidates sharing the same pinyin token sequence."""

    pinyin_tokens: tuple[str, ...]
    definition: str

    @property
    def pinyin_numbered(self) -> str:
        """Return grouped pinyin tokens rendered as a space-separated string."""

        return " ".join(self.pinyin_tokens)


def split_numbered_variants(numbered: str) -> list[tuple[str, ...]]:
    """Split slash-delimited numbered pinyin variants into token tuples.

    Args:
        numbered: Numbered pinyin that may contain ``/`` between variants.

    Returns:
        List of variant token tuples with empty segments removed.
    """

    variants: list[tuple[str, ...]] = []
    for part in numbered.split("/"):
        tokens = tuple(token for token in part.strip().split() if token)
        if tokens:
            variants.append(tokens)
    return variants


def tone_insensitive_tokens(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """Drop trailing tone numbers from numbered pinyin tokens.

    Args:
        tokens: Numbered pinyin tokens.

    Returns:
        Tone-insensitive base tokens preserving token count/order.
    """

    return tuple(token[:-1] if token and token[-1].isdigit() else token for token in tokens)


def group_candidates(entries: tuple[CedictEntry, ...]) -> tuple[CandidateGroup, ...]:
    """Group entries by pinyin and merge duplicate definitions deterministically.

    Args:
        entries: Raw entries for a given word.

    Returns:
        Candidate groups with one row per distinct pinyin token sequence.
    """

    grouped_defs: dict[tuple[str, ...], set[str]] = {}
    for entry in entries:
        grouped_defs.setdefault(entry.pinyin_tokens, set()).add(entry.definition)

    groups: list[CandidateGroup] = []
    for pinyin_tokens, defs in grouped_defs.items():
        definition = " | ".join(sorted(d for d in defs if d))
        groups.append(CandidateGroup(pinyin_tokens=pinyin_tokens, definition=definition))

    groups.sort(key=lambda item: (item.pinyin_tokens, item.definition))
    return tuple(groups)


def exact_match(
    groups: tuple[CandidateGroup, ...],
    source_variants: tuple[tuple[str, ...], ...],
) -> CandidateGroup | None:
    """Return the first exact pinyin match based on source variant order.

    Args:
        groups: Candidate groups for one Hanzi word.
        source_variants: Source numbered pinyin variants in original order.

    Returns:
        The selected exact match, or ``None`` if no exact match exists.
    """

    by_tokens = {group.pinyin_tokens: group for group in groups}
    for variant in source_variants:
        if variant in by_tokens:
            return by_tokens[variant]
    return None


def tone_insensitive_matches(
    groups: tuple[CandidateGroup, ...],
    source_variants: tuple[tuple[str, ...], ...],
) -> tuple[CandidateGroup, ...]:
    """Find candidates whose tone-insensitive tokens match source variants.

    Args:
        groups: Candidate groups for one Hanzi word.
        source_variants: Source numbered variants.

    Returns:
        Candidate groups that match any source variant after removing tones.
    """

    source_bases = {tone_insensitive_tokens(variant) for variant in source_variants}
    matched = [
        group for group in groups if tone_insensitive_tokens(group.pinyin_tokens) in source_bases
    ]
    return tuple(matched)
