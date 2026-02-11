"""Repository for tone-insensitive disambiguation overrides."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DisambiguationRepository:
    """Lookup repository for resolving multi-candidate tone-insensitive matches.

    Each record maps ``(word, source_pinyin_numbered)`` to a chosen CC-CEDICT
    pinyin string.
    """

    path: Path

    def load(self) -> dict[tuple[str, str], str]:
        """Load mapping rows from a TSV file.

        The parser accepts either a header row with columns
        ``word``, ``source_pinyin_numbered``, ``selected_cedict_pinyin`` or
        plain three-column rows in that order.

        Returns:
            Mapping keyed by ``(word, source_pinyin_numbered)``.
        """

        if not self.path.exists():
            return {}

        with self.path.open("r", encoding="utf-8") as handle:
            raw_lines = [line.rstrip("\n") for line in handle]

        lines = [line for line in raw_lines if line.strip() and not line.lstrip().startswith("#")]
        if not lines:
            return {}

        mapping: dict[tuple[str, str], str] = {}
        header_cells = [cell.strip() for cell in lines[0].split("\t")]
        expected = {"word", "source_pinyin_numbered", "selected_cedict_pinyin"}

        if expected.issubset(set(header_cells)):
            idx_word = header_cells.index("word")
            idx_source = header_cells.index("source_pinyin_numbered")
            idx_selected = header_cells.index("selected_cedict_pinyin")
            data_lines = lines[1:]
        else:
            idx_word = 0
            idx_source = 1
            idx_selected = 2
            data_lines = lines

        for line in data_lines:
            cells = [cell.strip() for cell in line.split("\t")]
            if len(cells) <= max(idx_word, idx_source, idx_selected):
                continue
            word = cells[idx_word]
            source = cells[idx_source]
            selected = cells[idx_selected]
            if not word or not source or not selected:
                continue
            mapping[(word, source)] = selected

        return mapping
