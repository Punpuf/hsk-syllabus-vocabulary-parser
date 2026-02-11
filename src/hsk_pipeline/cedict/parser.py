"""Parsing utilities for CC-CEDICT and compatible patch files."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterator

CEDICT_ENTRY_RE = re.compile(r"^(\S+)\s+(\S+)\s+\[([^]]+)]\s*/(.*)/\s*$")
CEDICT_ALSO_PR_RE = re.compile(r"also pr\. \[([^]]+)]")
NUMBERED_SYLLABLE_RE = re.compile(r"[a-zü]+[1-5]")


@dataclass(frozen=True)
class CedictEntry:
    """One normalized dictionary record for a specific word and pinyin tokenization.

    Each record is keyed by simplified/traditional word form plus a numbered
    pinyin token sequence. Definition text is stored as slash-delimited glosses
    joined into a single ``; `` separated string for stable TSV output.
    """

    word: str
    pinyin_tokens: tuple[str, ...]
    definition: str

    @property
    def pinyin_numbered(self) -> str:
        """Return the canonical space-separated numbered pinyin string."""

        return " ".join(self.pinyin_tokens)


def normalize_cedict_syllable(token: str) -> str | None:
    """Normalize one CC-CEDICT pinyin token to lowercase numbered format.

    CC-CEDICT occasionally uses ``u:`` or ``v`` for ``ü``. The function applies
    those substitutions and validates the final token shape.

    Args:
        token: Raw token from the pinyin bracket payload.

    Returns:
        A normalized token such as ``lü4`` encoded as ``lü4`` with trailing tone
        number, or ``None`` when the token is malformed.
    """

    token = token.strip()
    if not token:
        return None
    token = token.replace("u:", "ü").replace("U:", "ü")
    token = token.replace("v", "ü").replace("V", "ü")
    token = token.lower()
    if not NUMBERED_SYLLABLE_RE.fullmatch(token):
        return None
    return token


def _parse_pinyin_tokens(payload: str) -> tuple[str, ...] | None:
    """Parse bracketed pinyin payload into normalized numbered tokens.

    Args:
        payload: Raw pinyin string inside ``[...]`` from a CEDICT line.

    Returns:
        Tuple of normalized numbered syllables, or ``None`` if any token fails.
    """

    tokens: list[str] = []
    for token in payload.split():
        normalized = normalize_cedict_syllable(token)
        if normalized is None:
            return None
        tokens.append(normalized)
    if not tokens:
        return None
    return tuple(tokens)


def extract_additional_pinyin(definition_payload: str) -> list[tuple[str, ...]]:
    """Extract ``also pr. [...]`` alternates from the definition payload.

    Args:
        definition_payload: Raw gloss payload captured from a CEDICT line.

    Returns:
        Normalized alternate pinyin token tuples discovered in the text.
    """

    alternates: list[tuple[str, ...]] = []
    for match in CEDICT_ALSO_PR_RE.finditer(definition_payload):
        parsed = _parse_pinyin_tokens(match.group(1))
        if parsed is not None:
            alternates.append(parsed)
    return alternates


def parse_cedict_lines(lines: Iterator[str]) -> list[CedictEntry]:
    """Parse CC-CEDICT lines into normalized entries for simp/trad forms.

    The parser ignores comments and malformed lines. For each valid line, both
    traditional and simplified forms are emitted and ``also pr.`` alternates are
    included as additional entries sharing the same definition.

    Args:
        lines: Iterator of raw dictionary lines.

    Returns:
        Flat list of parsed entries.
    """

    entries: list[CedictEntry] = []
    for line in lines:
        if not line or line.startswith("#"):
            continue
        match = CEDICT_ENTRY_RE.match(line.strip())
        if not match:
            continue

        trad, simp, pinyin_field, definition_payload = match.groups()
        primary_tokens = _parse_pinyin_tokens(pinyin_field)
        if primary_tokens is None:
            continue

        glosses = [part for part in definition_payload.split("/") if part]
        definition = "; ".join(glosses).strip()

        token_sets = [primary_tokens, *extract_additional_pinyin(definition_payload)]
        words = {trad, simp}
        for word in words:
            for tokens in token_sets:
                if len(tokens) != len(word):
                    continue
                entries.append(
                    CedictEntry(
                        word=word,
                        pinyin_tokens=tokens,
                        definition=definition,
                    )
                )

    return entries
