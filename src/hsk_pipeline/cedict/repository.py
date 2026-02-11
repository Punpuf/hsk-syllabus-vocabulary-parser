"""Repository utilities for querying CC-CEDICT data structures."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from hsk_pipeline.cedict.parser import CedictEntry, parse_cedict_lines


@dataclass(frozen=True)
class CedictRepository:
    """Read-only repository that exposes indexed CC-CEDICT lookup views.

    The repository parses CEDICT-compatible ``.u8`` content once and builds
    indices for word-level and Hanzi-level pinyin lookups used by Stage 2 and
    Stage 3. Instances are path-scoped and deterministic.
    """

    path: Path

    @cached_property
    def entries(self) -> tuple[CedictEntry, ...]:
        """Load and cache normalized entries from disk.

        Returns:
            Immutable tuple of parsed entries.

        Raises:
            FileNotFoundError: If the configured CEDICT file path does not exist.
        """

        if not self.path.exists():
            raise FileNotFoundError(f"CC-CEDICT file not found: {self.path}")

        with self.path.open("r", encoding="utf-8") as handle:
            parsed = parse_cedict_lines(handle)

        deduped: dict[tuple[str, tuple[str, ...], str], CedictEntry] = {}
        for entry in parsed:
            key = (entry.word, entry.pinyin_tokens, entry.definition)
            deduped[key] = entry
        return tuple(deduped.values())

    @cached_property
    def entries_by_word(self) -> dict[str, tuple[CedictEntry, ...]]:
        """Build and cache a word-indexed entry map.

        Returns:
            Dictionary mapping Hanzi words to immutable entry tuples.
        """

        mapping: dict[str, list[CedictEntry]] = {}
        for entry in self.entries:
            mapping.setdefault(entry.word, []).append(entry)
        return {word: tuple(items) for word, items in mapping.items()}

    @cached_property
    def word_syllable_map(self) -> dict[str, set[tuple[str, ...]]]:
        """Build word -> allowed numbered syllable tuples lookup for Stage 2.

        Returns:
            Dictionary mapping full words to numbered token sequences.
        """

        mapping: dict[str, set[tuple[str, ...]]] = {}
        for entry in self.entries:
            mapping.setdefault(entry.word, set()).add(entry.pinyin_tokens)
        return mapping

    @cached_property
    def hanzi_syllable_map(self) -> dict[str, set[str]]:
        """Build Hanzi -> candidate numbered syllables lookup for alignment.

        The algorithm mirrors prior behavior: multi-character words only add a
        new syllable for a Hanzi when that Hanzi does not already have that base
        syllable (tone-insensitive), reducing over-permissive ambiguity.

        Returns:
            Dictionary mapping each Hanzi to a set of numbered syllables.
        """

        mapping: dict[str, set[str]] = {}
        multi_char_entries: list[tuple[str, tuple[str, ...]]] = []

        for entry in self.entries:
            if len(entry.word) == 1 and len(entry.pinyin_tokens) == 1:
                mapping.setdefault(entry.word, set()).add(entry.pinyin_tokens[0])
            elif len(entry.word) == len(entry.pinyin_tokens):
                multi_char_entries.append((entry.word, entry.pinyin_tokens))

        for word, pinyin_tokens in multi_char_entries:
            for hanzi, syllable in zip(word, pinyin_tokens):
                if hanzi not in mapping:
                    mapping.setdefault(hanzi, set()).add(syllable)
                    continue
                existing_bases = {item[:-1] for item in mapping[hanzi]}
                if syllable[:-1] not in existing_bases:
                    mapping[hanzi].add(syllable)

        for char, base in {"一": "yi", "不": "bu"}.items():
            options = mapping.setdefault(char, set())
            for tone in range(1, 6):
                options.add(f"{base}{tone}")

        return mapping

    def entries_for_word(self, word: str) -> tuple[CedictEntry, ...]:
        """Return normalized entries for a word.

        Args:
            word: Hanzi word key.

        Returns:
            Tuple of entries for ``word``; empty tuple when absent.
        """

        return self.entries_by_word.get(word, ())
