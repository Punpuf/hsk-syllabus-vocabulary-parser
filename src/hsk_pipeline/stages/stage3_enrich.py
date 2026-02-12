"""Stage 3: Resolve CC-CEDICT pinyin/definition for each numbered row."""

from __future__ import annotations

from dataclasses import dataclass
import re

from hsk_pipeline.cedict.disambiguation import DisambiguationRepository
from hsk_pipeline.cedict.matcher import (
    CandidateGroup,
    exact_match,
    group_candidates,
    split_numbered_variants,
    tone_insensitive_matches,
)
from hsk_pipeline.cedict.repository import CedictRepository
from hsk_pipeline.models import (
    EnrichedRow,
    NoMatchItem,
    NumberedRow,
    PatchedMatch,
    ResolutionReport,
    ToneInsensitiveMultiMatch,
    ToneInsensitiveUniqueMatch,
)

CJK_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass(frozen=True)
class _Resolution:
    """Internal selected candidate with provenance metadata."""

    candidate: CandidateGroup
    branch: str


def _lookup_word(word: str) -> str:
    """Normalize a row word into Hanzi-only form for dictionary lookup.

    Source rows may include sense suffixes like ``1``/``2`` (for example,
    ``点1`` and ``点2``). CC-CEDICT keys do not include these suffixes, so this
    helper strips non-Hanzi characters before lookup.

    Args:
        word: Source row word.

    Returns:
        Hanzi-only lookup key, or the original word if no Hanzi is present.
    """

    hanzi_only = "".join(ch for ch in word if CJK_RE.fullmatch(ch))
    return hanzi_only or word


def _resolve_from_repo(
    row: NumberedRow,
    repo: CedictRepository,
    disambiguation_map: dict[tuple[str, str], str],
) -> tuple[_Resolution | None, str | None, tuple[CandidateGroup, ...]]:
    """Resolve a row against one repository using staged matching rules.

    Args:
        row: Stage 2 row being enriched.
        repo: Dictionary repository to query.
        disambiguation_map: Optional selected pinyin overrides for multi-match
            tone-insensitive cases.

    Returns:
        Tuple of ``(resolution, unresolved_note, tone_candidates)`` where:
        - ``resolution`` is selected candidate+branch or ``None``.
        - ``unresolved_note`` explains unresolved reason, if any.
        - ``tone_candidates`` is the tone-insensitive candidate list (used for
          reporting when disambiguation was required).
    """

    source_variants = tuple(split_numbered_variants(row.pinyin_numbered))
    if not source_variants:
        return None, "empty_source_pinyin_numbered", ()

    groups = group_candidates(repo.entries_for_word(_lookup_word(row.word)))
    if not groups:
        return None, "no_word_entry", ()

    exact = exact_match(groups, source_variants)
    if exact is not None:
        return _Resolution(candidate=exact, branch="exact"), None, ()

    tone_candidates = tone_insensitive_matches(groups, source_variants)
    if len(tone_candidates) == 1:
        return (
            _Resolution(candidate=tone_candidates[0], branch="tone_insensitive_unique"),
            None,
            tone_candidates,
        )

    if len(tone_candidates) > 1:
        selected = disambiguation_map.get((row.word, row.pinyin_numbered))
        if selected:
            for candidate in tone_candidates:
                if candidate.pinyin_numbered == selected:
                    return (
                        _Resolution(candidate=candidate, branch="tone_insensitive_multi"),
                        None,
                        tone_candidates,
                    )
            return None, f"disambiguation_selected_not_in_candidates:{selected}", tone_candidates

        candidate_list = ", ".join(candidate.pinyin_numbered for candidate in tone_candidates)
        return None, f"tone_insensitive_multiple_candidates:{candidate_list}", tone_candidates

    return None, "no_pinyin_match", ()


def enrich_with_cedict(
    rows: list[NumberedRow],
    cedict_repo: CedictRepository,
    disambiguation_repo: DisambiguationRepository,
    patch_repo: CedictRepository,
    allow_unresolved: bool = False,
) -> tuple[list[EnrichedRow], ResolutionReport]:
    """Add CC-CEDICT enrichment fields to Stage 2 rows.

    Resolution order per row:
    1) exact numbered match in main CC-CEDICT,
    2) tone-insensitive unique match in main CC-CEDICT,
    3) tone-insensitive multiple match resolved by disambiguation TSV,
    4) fallback to patch dictionary with same matching strategy,
    5) unresolved (error by default).

    Args:
        rows: Stage 2 rows.
        cedict_repo: Main CC-CEDICT repository.
        disambiguation_repo: Repository for multi-match overrides.
        patch_repo: Patch dictionary repository in CEDICT format.
        allow_unresolved: Whether unresolved rows should be kept instead of
            raising an error.

    Returns:
        Final enriched rows and a structured resolution report.

    Raises:
        ValueError: If unresolved rows exist and ``allow_unresolved`` is false.
    """

    disambiguation_map = disambiguation_repo.load()

    enriched_rows: list[EnrichedRow] = []
    tone_unique: list[ToneInsensitiveUniqueMatch] = []
    tone_multi: list[ToneInsensitiveMultiMatch] = []
    patched: list[PatchedMatch] = []
    no_match: list[NoMatchItem] = []

    for row in rows:
        resolution, note, tone_candidates = _resolve_from_repo(
            row=row,
            repo=cedict_repo,
            disambiguation_map=disambiguation_map,
        )

        if resolution is None and note in {"no_word_entry", "no_pinyin_match"}:
            patch_resolution, patch_note, patch_tone_candidates = _resolve_from_repo(
                row=row,
                repo=patch_repo,
                disambiguation_map=disambiguation_map,
            )
            if patch_resolution is not None:
                resolution = patch_resolution
                note = None
                patched.append(
                    PatchedMatch(
                        word_index=row.word_index,
                        word=row.word,
                        source_pinyin_numbered=row.pinyin_numbered,
                        selected_cedict_pinyin=patch_resolution.candidate.pinyin_numbered,
                    )
                )
                tone_candidates = patch_tone_candidates
            elif patch_note not in {"no_word_entry", "no_pinyin_match"}:
                note = f"patch_{patch_note}"

        if resolution is None:
            no_match.append(
                NoMatchItem(
                    word_index=row.word_index,
                    word=row.word,
                    source_pinyin=row.pinyin,
                    source_pinyin_numbered=row.pinyin_numbered,
                    notes=note or "unresolved",
                )
            )
            if allow_unresolved:
                enriched_rows.append(
                    EnrichedRow(
                        word_index=row.word_index,
                        level=row.level,
                        word=row.word,
                        pinyin=row.pinyin,
                        part_of_speech=row.part_of_speech,
                        pinyin_numbered=row.pinyin_numbered,
                        pinyin_cc_cedict="",
                        traditional_cc_cedict="",
                        definition_cc_cedict="",
                    )
                )
            continue

        if resolution.branch == "tone_insensitive_unique":
            tone_unique.append(
                ToneInsensitiveUniqueMatch(
                    word_index=row.word_index,
                    word=row.word,
                    source_pinyin=row.pinyin,
                    source_pinyin_numbered=row.pinyin_numbered,
                    selected_cedict_pinyin=resolution.candidate.pinyin_numbered,
                )
            )

        if resolution.branch == "tone_insensitive_multi":
            tone_multi.append(
                ToneInsensitiveMultiMatch(
                    word_index=row.word_index,
                    word=row.word,
                    source_pinyin=row.pinyin,
                    source_pinyin_numbered=row.pinyin_numbered,
                    candidate_cedict_pinyin=tuple(
                        sorted(candidate.pinyin_numbered for candidate in tone_candidates)
                    ),
                    selected_cedict_pinyin=resolution.candidate.pinyin_numbered,
                )
            )

        enriched_rows.append(
            EnrichedRow(
                word_index=row.word_index,
                level=row.level,
                word=row.word,
                pinyin=row.pinyin,
                part_of_speech=row.part_of_speech,
                pinyin_numbered=row.pinyin_numbered,
                pinyin_cc_cedict=resolution.candidate.pinyin_numbered,
                traditional_cc_cedict="/".join(resolution.candidate.traditional_forms),
                definition_cc_cedict=resolution.candidate.definition,
            )
        )

    report = ResolutionReport(
        tone_insensitive_unique=tuple(tone_unique),
        tone_insensitive_multi=tuple(tone_multi),
        patched=tuple(patched),
        no_match=tuple(no_match),
    )

    if report.no_match and not allow_unresolved:
        preview = "\n".join(
            f"- idx={item.word_index} word={item.word} source={item.source_pinyin_numbered} reason={item.notes}"
            for item in report.no_match[:25]
        )
        remaining = len(report.no_match) - min(25, len(report.no_match))
        extra = f"\n- ... and {remaining} more" if remaining > 0 else ""
        raise ValueError(
            "Unresolved CC-CEDICT enrichment rows found. "
            "Add disambiguation/patch entries or use --allow-unresolved.\n"
            f"{preview}{extra}"
        )

    return enriched_rows, report
