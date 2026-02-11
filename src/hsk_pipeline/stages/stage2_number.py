"""Stage 2: Generate numbered pinyin aligned to Hanzi using CC-CEDICT."""

from __future__ import annotations

import re
import unicodedata
from typing import Sequence

from pypinyin import constants as pypinyin_constants

from hsk_pipeline.cedict.repository import CedictRepository
from hsk_pipeline.models import NumberedRow, RawRow

TONE_MARKS = {
    "ā": ("a", 1),
    "á": ("a", 2),
    "ǎ": ("a", 3),
    "à": ("a", 4),
    "ē": ("e", 1),
    "é": ("e", 2),
    "ě": ("e", 3),
    "è": ("e", 4),
    "ī": ("i", 1),
    "í": ("i", 2),
    "ǐ": ("i", 3),
    "ì": ("i", 4),
    "ō": ("o", 1),
    "ó": ("o", 2),
    "ǒ": ("o", 3),
    "ò": ("o", 4),
    "ū": ("u", 1),
    "ú": ("u", 2),
    "ǔ": ("u", 3),
    "ù": ("u", 4),
    "ǖ": ("ü", 1),
    "ǘ": ("ü", 2),
    "ǚ": ("ü", 3),
    "ǜ": ("ü", 4),
    "ń": ("n", 2),
    "ň": ("n", 3),
    "ǹ": ("n", 4),
    "ḿ": ("m", 2),
    "ê": ("e", 5),
    "Ê": ("e", 5),
}

SEPARATOR_CHARS = set("-/'’·•")
PRESERVE_SEPARATORS = {"/"}
EXTRA_VALID_SYLLABLES = {"m", "n", "ng", "hm", "hng", "r"}
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
NUMBERED_SYLLABLE_RE = re.compile(r"[a-zü]+[1-5]")
LETTER_PATTERN = re.compile(r"[a-zü]+")


def _extract_hanzi_chars(word: str) -> list[str]:
    """Extract CJK Hanzi characters from a word string.

    Args:
        word: Source word field, which may include non-Hanzi suffix markers.

    Returns:
        Ordered list of Hanzi characters used for pinyin alignment.
    """

    return [char for char in word if CJK_RE.fullmatch(char)]


def _strip_tone_marks(syllable: str) -> str:
    """Normalize one pinyin chunk by removing tone marks and lowercasing.

    Args:
        syllable: Pinyin chunk that may contain tone-marked vowels.

    Returns:
        Tone-free lowercase pinyin where ``v`` is normalized to ``ü``.
    """

    chars: list[str] = []
    for ch in syllable:
        if ch in TONE_MARKS:
            chars.append(TONE_MARKS[ch][0])
        elif ch.lower() == "v":
            chars.append("ü")
        else:
            chars.append(ch)
    return "".join(chars).lower()


def _tokenize_pinyin(pinyin: str) -> list[tuple[str, bool]]:
    """Split pinyin into token/separator pairs.

    Args:
        pinyin: Raw pinyin string.

    Returns:
        List of ``(token, is_separator)`` where slash separators are preserved
        and other separators/whitespace become boundaries.
    """

    tokens: list[tuple[str, bool]] = []
    buf: list[str] = []

    def flush_buffer() -> None:
        if buf:
            tokens.append(("".join(buf), False))
            buf.clear()

    for ch in pinyin:
        if ch.isspace() or ch in SEPARATOR_CHARS:
            flush_buffer()
            if ch in PRESERVE_SEPARATORS:
                tokens.append((ch, True))
            continue
        buf.append(ch)

    flush_buffer()
    return tokens


def _collect_valid_syllables() -> list[str]:
    """Collect valid pinyin syllables from pypinyin dictionaries.

    Returns:
        Length-descending syllable list used by the greedy+memo segmenter.
    """

    syllables: set[str] = set()

    for value in pypinyin_constants.PINYIN_DICT.values():
        for item in str(value).split(","):
            base = _strip_tone_marks(item)
            if base:
                syllables.add(base)

    for phrase in pypinyin_constants.PHRASES_DICT.values():
        for syllable_group in phrase:
            for item in syllable_group:
                base = _strip_tone_marks(item)
                if base:
                    syllables.add(base)

    extended = {s + "r" for s in syllables if s and not s.endswith("r")}
    syllables.update(extended)
    syllables.update(EXTRA_VALID_SYLLABLES)

    return sorted(syllables, key=len, reverse=True)


VALID_SYLLABLES = _collect_valid_syllables()


def _segment_syllables(base: str) -> list[tuple[int, int, str]]:
    """Segment a tone-free pinyin chunk into valid syllables.

    Args:
        base: Tone-free pinyin chunk such as ``ba ba`` collapsed to ``baba``.

    Returns:
        List of ``(start, end, syllable_base)`` boundaries.

    Raises:
        ValueError: If no valid complete segmentation can be found.
    """

    if not base:
        return []

    memo: dict[int, list[tuple[int, int, str]] | None] = {}

    def helper(idx: int) -> list[tuple[int, int, str]] | None:
        if idx == len(base):
            return []
        if idx in memo:
            return memo[idx]

        for syllable in VALID_SYLLABLES:
            if base.startswith(syllable, idx):
                next_idx = idx + len(syllable)
                rest = helper(next_idx)
                if rest is not None:
                    result = [(idx, next_idx, syllable)] + rest
                    memo[idx] = result
                    return result

        memo[idx] = None
        return None

    result = helper(0)
    if result is None:
        raise ValueError(f"Unable to segment pinyin '{base}' into valid syllables.")
    return result


def _segment_pinyin_with_hanzi(
    tokens: Sequence[str],
    hanzi_chars: Sequence[str],
    hanzi_map: dict[str, set[str]],
    word_map: dict[str, set[tuple[str, ...]]],
    word_index: str,
) -> list[str]:
    """Segment pinyin tokens while aligning each syllable to Hanzi sequence.

    Args:
        tokens: Tokenized pinyin chunks for one pronunciation variant.
        hanzi_chars: Hanzi sequence extracted from the row word.
        hanzi_map: Hanzi -> allowed numbered syllables lookup.
        word_map: Word -> allowed syllable tuple lookup for disambiguation.
        word_index: Source row index for error messages.

    Returns:
        A single numbered syllable sequence aligned with ``hanzi_chars``.

    Raises:
        ValueError: If alignment fails or remains ambiguous after dictionary-based
            disambiguation.
    """

    allowed = {char: hanzi_map[char] for char in hanzi_chars}
    allowed_bases = {
        char: {syllable[:-1] for syllable in syllables} for char, syllables in allowed.items()
    }

    def parse_token(token: str) -> tuple[str, list[int]]:
        base_chars: list[str] = []
        tone_marks: list[int] = []
        for ch in token:
            if ch in TONE_MARKS:
                base_char, tone = TONE_MARKS[ch]
                base_chars.append(base_char)
                tone_marks.append(tone)
            else:
                base_chars.append("ü" if ch.lower() == "v" else ch)
                tone_marks.append(0)
        base = "".join(base_chars).lower()
        return base, tone_marks

    def segment_token(
        base: str,
        tone_marks: Sequence[int],
        start_char_idx: int,
    ) -> list[tuple[list[str], int]]:
        if len(base) != len(tone_marks):
            raise ValueError(
                f"Pinyin normalization mismatch for word index {word_index}: "
                "base/tone length differs."
            )

        memo: dict[tuple[int, int], list[tuple[list[str], int]]] = {}

        def helper(base_idx: int, char_idx: int) -> list[tuple[list[str], int]]:
            key = (base_idx, char_idx)
            if key in memo:
                return memo[key]

            if base_idx == len(base):
                return [([], char_idx)]
            if char_idx >= len(hanzi_chars):
                return []

            char = hanzi_chars[char_idx]
            solutions: list[tuple[list[str], int]] = []
            for syllable in VALID_SYLLABLES:
                if not base.startswith(syllable, base_idx):
                    continue
                end_idx = base_idx + len(syllable)
                tones = {tone for tone in tone_marks[base_idx:end_idx] if tone}
                if len(tones) > 1:
                    continue
                tone = tones.pop() if tones else 5
                numbered = f"{syllable}{tone}"

                if (
                    syllable.endswith("r")
                    and char_idx + 1 < len(hanzi_chars)
                    and hanzi_chars[char_idx + 1] == "儿"
                ):
                    base_without_r = syllable[:-1]
                    erhua_possible = (
                        base_without_r
                        and base_without_r in allowed_bases[char]
                        and ("r5" in allowed["儿"])
                    )
                    if erhua_possible:
                        preferred = False
                        for rest, next_char_idx in helper(end_idx, char_idx + 2):
                            solutions.append(
                                ([f"{base_without_r}{tone}", "r5"] + rest, next_char_idx)
                            )
                            preferred = True
                            if len(solutions) > 1:
                                memo[key] = solutions
                                return solutions
                        if preferred:
                            memo[key] = solutions
                            return solutions
                        for rest, next_char_idx in helper(end_idx, char_idx + 2):
                            solutions.append(([numbered] + rest, next_char_idx))
                            if len(solutions) > 1:
                                memo[key] = solutions
                                return solutions
                        if solutions:
                            memo[key] = solutions
                            return solutions

                if syllable in EXTRA_VALID_SYLLABLES:
                    for rest, next_char_idx in helper(end_idx, char_idx + 1):
                        solutions.append(([numbered] + rest, next_char_idx))
                        if len(solutions) > 1:
                            memo[key] = solutions
                            return solutions
                    continue

                if len(hanzi_chars) == 1 and syllable not in allowed_bases[char]:
                    for rest, next_char_idx in helper(end_idx, char_idx + 1):
                        solutions.append(([numbered] + rest, next_char_idx))
                        if len(solutions) > 1:
                            memo[key] = solutions
                            return solutions
                    continue

                if syllable in allowed_bases[char]:
                    for rest, next_char_idx in helper(end_idx, char_idx + 1):
                        solutions.append(([numbered] + rest, next_char_idx))
                        if len(solutions) > 1:
                            memo[key] = solutions
                            return solutions

            memo[key] = solutions
            return solutions

        return helper(0, start_char_idx)

    memo: dict[tuple[int, int], list[list[str]]] = {}

    def helper(token_idx: int, char_idx: int) -> list[list[str]]:
        key = (token_idx, char_idx)
        if key in memo:
            return memo[key]

        if token_idx == len(tokens):
            return [[]] if char_idx == len(hanzi_chars) else []

        token = tokens[token_idx]
        base, tone_marks = parse_token(token)
        if not base:
            return []

        solutions: list[list[str]] = []
        for syllables, next_char_idx in segment_token(base, tone_marks, char_idx):
            for rest in helper(token_idx + 1, next_char_idx):
                solutions.append(syllables + rest)
                if len(solutions) > 1:
                    memo[key] = solutions
                    return solutions

        memo[key] = solutions
        return solutions

    solutions = helper(0, 0)
    if not solutions:
        raise ValueError(
            f"Unable to align pinyin to Hanzi '{''.join(hanzi_chars)}' "
            f"for word index {word_index}."
        )
    if len(solutions) > 1:
        word = "".join(hanzi_chars)
        candidates = word_map.get(word)
        if candidates:
            candidate_bases = {tuple(syllable[:-1] for syllable in seq) for seq in candidates}
            filtered = [
                solution
                for solution in solutions
                if tuple(syllable[:-1] for syllable in solution) in candidate_bases
            ]
            if len(filtered) == 1:
                return filtered[0]
            if filtered:
                solutions = filtered
        formatted = "; ".join(" ".join(syllables) for syllables in solutions)
        raise ValueError(
            f"Ambiguous pinyin alignment for word index {word_index} "
            f"('{''.join(hanzi_chars)}'): {len(solutions)} valid segmentations "
            f"({formatted})."
        )
    return solutions[0]


def _pinyin_numbered_basic(pinyin: str, word_index: str) -> str:
    """Convert pinyin to numbered format without Hanzi alignment constraints.

    Args:
        pinyin: Source pinyin text possibly containing tone marks and separators.
        word_index: Source index used for diagnostics.

    Returns:
        Numbered pinyin with syllables space-separated and slash variants kept.
    """

    pinyin = unicodedata.normalize("NFC", pinyin).lower()
    tokens = _tokenize_pinyin(pinyin)
    if not tokens:
        raise ValueError(f"Empty pinyin for word index {word_index}.")

    numbered_syllables: list[str] = []
    normalized_parts: list[str] = []
    output_parts: list[str] = []

    for token, is_separator in tokens:
        if is_separator:
            output_parts.append(token)
            continue

        chunk = token
        base_chars: list[str] = []
        tone_marks: list[int] = []
        for ch in chunk:
            if ch in TONE_MARKS:
                base_char, tone = TONE_MARKS[ch]
                base_chars.append(base_char)
                tone_marks.append(tone)
            else:
                base_chars.append("ü" if ch.lower() == "v" else ch)
                tone_marks.append(0)

        base = "".join(base_chars).lower()
        normalized_parts.append(base)
        boundaries = _segment_syllables(base)

        chunk_syllables: list[str] = []
        for start, end, syllable in boundaries:
            tones = {tone for tone in tone_marks[start:end] if tone}
            if len(tones) > 1:
                raise ValueError(
                    f"Multiple tone marks in syllable '{syllable}' "
                    f"for word index {word_index} (pinyin '{pinyin}')."
                )
            tone = tones.pop() if tones else 5
            chunk_syllables.append(f"{syllable}{tone}")

        numbered_syllables.extend(chunk_syllables)
        output_parts.append(" ".join(chunk_syllables))

    normalized_joined = "".join(normalized_parts)
    numbered_joined = "".join(syllable[:-1] for syllable in numbered_syllables)
    if normalized_joined != numbered_joined:
        raise ValueError(
            f"Pinyin normalization mismatch for word index {word_index}: "
            f"'{normalized_joined}' != '{numbered_joined}'."
        )

    for syllable in numbered_syllables:
        if not LETTER_PATTERN.fullmatch(syllable[:-1]):
            raise ValueError(f"Invalid syllable '{syllable}' for word index {word_index}.")

    output = ""
    for part in output_parts:
        if part in PRESERVE_SEPARATORS:
            output = output.rstrip() + part
            continue
        if output and not output.endswith((" ",) + tuple(PRESERVE_SEPARATORS)):
            output += " "
        output += part

    return output.strip()


def pinyin_numbered(
    pinyin: str,
    word_index: str,
    word: str,
    cedict_repo: CedictRepository,
) -> str:
    """Convert source pinyin to numbered format aligned to Hanzi.

    Args:
        pinyin: Source tone-marked pinyin.
        word_index: Source row index for diagnostics.
        word: Source Hanzi word.
        cedict_repo: Repository used for Hanzi/word syllable constraints.

    Returns:
        Numbered pinyin string for the row.

    Raises:
        ValueError: If alignment or normalization fails.
    """

    hanzi_chars = _extract_hanzi_chars(word)
    if not hanzi_chars:
        return _pinyin_numbered_basic(pinyin, word_index)

    hanzi_map = cedict_repo.hanzi_syllable_map
    missing = [char for char in hanzi_chars if char not in hanzi_map]
    if missing:
        missing_display = " ".join(sorted(set(missing)))
        raise ValueError(
            f"Missing CC-CEDICT pinyin mapping for Hanzi '{missing_display}' "
            f"(word index {word_index})."
        )

    word_map = cedict_repo.word_syllable_map
    pinyin = unicodedata.normalize("NFC", pinyin).lower()
    variants = [part.strip() for part in pinyin.split("/") if part.strip()]
    numbered_variants: list[str] = []

    for variant in variants:
        tokens = [token for token, is_separator in _tokenize_pinyin(variant) if not is_separator]
        if not tokens:
            raise ValueError(f"Empty pinyin for word index {word_index}.")

        normalized_parts: list[str] = []
        for token in tokens:
            base_chars: list[str] = []
            for ch in token:
                if ch in TONE_MARKS:
                    base_char, _ = TONE_MARKS[ch]
                    base_chars.append(base_char)
                else:
                    base_chars.append("ü" if ch.lower() == "v" else ch)
            normalized_parts.append("".join(base_chars).lower())
        normalized_joined = "".join(normalized_parts)

        syllables = _segment_pinyin_with_hanzi(
            tokens=tokens,
            hanzi_chars=hanzi_chars,
            hanzi_map=hanzi_map,
            word_map=word_map,
            word_index=word_index,
        )

        numbered_joined = "".join(syllable[:-1] for syllable in syllables)
        if normalized_joined != numbered_joined:
            raise ValueError(
                f"Pinyin normalization mismatch for word index {word_index}: "
                f"'{normalized_joined}' != '{numbered_joined}'."
            )

        numbered_variants.append(" ".join(syllables))

    return "/".join(numbered_variants).strip()


def add_pinyin_numbered(rows: list[RawRow], cedict_repo: CedictRepository) -> list[NumberedRow]:
    """Add ``pinyin_numbered`` to Stage 1 rows.

    Args:
        rows: Stage 1 rows parsed from source PDF.
        cedict_repo: Repository providing alignment constraints.

    Returns:
        Stage 2 rows with ``pinyin_numbered`` populated.
    """

    out: list[NumberedRow] = []
    for row in rows:
        numbered = pinyin_numbered(
            pinyin=row.pinyin,
            word_index=row.word_index,
            word=row.word,
            cedict_repo=cedict_repo,
        )
        out.append(
            NumberedRow(
                word_index=row.word_index,
                level=row.level,
                word=row.word,
                pinyin=row.pinyin,
                part_of_speech=row.part_of_speech,
                pinyin_numbered=numbered,
            )
        )
    return out
