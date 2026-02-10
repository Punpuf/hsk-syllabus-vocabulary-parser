#!/usr/bin/env python3
"""
HSK word list PDF -> TSV extractor.

Expected PDF formatting
- The word-list pages contain a header line equivalent to: "序号 等级 词语 拼音 词性".
- Each entry line begins with a numeric word index, then a level field, then the word,
  pinyin, and (optionally) part-of-speech.
- Level field formats supported:
  - single integer, e.g. "1"
  - integer with extra levels in full-width parentheses, e.g. "1（4）" or "3（4）（7-9）"
  - a range label, e.g. "7-9"
- Part-of-speech formatting for multi-level entries:
  - POS groups are separated by the Chinese enumeration separator "、".
  - If a POS group is wrapped in full-width parentheses, it maps to the corresponding
    extra level in the level field.
  - The non-parenthesized POS groups map to the base level.

Example mapping
Level field: "1（4）"
POS field:   "形、介、（动、量）"
Output rows: level=1 -> "形、介" and level=4 -> "动、量"

Pinyin numbering
- The output includes a `pinyin_numbered` column (e.g., "bàba" -> "ba4 ba5").
- The output also includes `pinyin_cc-cedict`, which normalizes Hanzi "不" to `bu4`
  and "一" to `yi1` based on character position.
- Pinyin is split into syllables, tone numbers are derived from accent marks, and
  neutral tone syllables use tone 5.
- Source pinyin may contain internal spaces for syllable boundaries (e.g.,
  "dǎ diànhuà"); the output `pinyin` column normalizes these as "dǎdiànhuà".
- Slash separators are preserved in the numbered output to reflect alternate readings.
- Other separator symbols (including dashes) are treated as syllable boundaries and removed.
- Syllabic interjections (e.g., "ng") are supported and treated as valid syllables.
- A small override table fixes known PDF extraction gaps where the Hanzi is missing.

Some source PDFs are extracts from a larger book; if your word list starts later in the
book (e.g., pages 4-278 of the original), use --page-start/--page-end to match that range.
"""

from __future__ import annotations

import argparse
from collections import Counter
import dataclasses
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Iterator, List, Sequence, Tuple

import pdfplumber
from pypinyin import constants as pypinyin_constants


ENTRY_RE = re.compile(r"^(\d+)\s+(\S+)\s+(.+)$")

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
EXTRA_VALID_SYLLABLES = {"m", "n", "ng", "hm", "hng"}
PINYIN_TOKEN_RE = re.compile(r"^[A-Za-zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜńňǹḿüÜêÊ]+$")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
CJK_ONLY_RE = re.compile(r"[\u4e00-\u9fff]+")
PAGE_MARKERS = {"汉", "国", "际", "考"}
CID_PATTERN = re.compile(r"\(cid:(\d+)\)")
VALID_HSK_LEVELS = {"1", "2", "3", "4", "5", "6", "7-9"}
WORD_VALID_RE = re.compile(r"^[一-鿿]+[12]?$")
PINYIN_EXCEPTION_CHARS = {"-", "’"}
PINYIN_ALLOWED_SEPARATORS = PRESERVE_SEPARATORS | PINYIN_EXCEPTION_CHARS

CID_CHAR_MAP = {
    "6656": "提",
    "11522": "盒",
    "11520": "盐",
    "15359": "藏",
    "6655": "描",
    "7680": "某",
    "11521": "监",
    "7679": "柏",
    "15360": "藐",
    "11519": "盏",
}

MISSING_WORD_OVERRIDES = {
    "1726": "提",
    "1844": "盐",
    "2092": "藏",
    "2785": "某",
    "10550": "盏",
}
LETTER_PATTERN = re.compile(r"[a-zü]+")
NUMBERED_SYLLABLE_RE = re.compile(r"[a-zü]+[1-5]")
CC_CEDICT_TONE_OVERRIDES = {"不": "bu4", "一": "yi1"}
ERHUA_MERGED_RE = re.compile(r"^([a-zü]+)r([1-5])$")


def _replace_cid_tokens(text: str) -> str:
    """Replace PDF CID placeholders with mapped Hanzi when available."""

    def repl(match: re.Match[str]) -> str:
        cid = match.group(1)
        return CID_CHAR_MAP.get(cid, match.group(0))

    return CID_PATTERN.sub(repl, text)


def _extract_hanzi_chars(word: str) -> List[str]:
    """Extract only CJK Hanzi characters from a word string."""
    return [char for char in word if CJK_RE.fullmatch(char)]


def _split_erhua_syllables(numbered_text: str) -> str:
    """
    Split merged erhua syllables into separate tokens in numbered pinyin.

    Examples:
        zher4 -> zhe4 r5
        dianr3 -> dian3 r5
    """
    matches = list(NUMBERED_SYLLABLE_RE.finditer(numbered_text.lower()))
    if not matches:
        return numbered_text

    out_parts: List[str] = []
    cursor = 0
    for match in matches:
        start = match.start()
        end = match.end()
        out_parts.append(numbered_text[cursor:start])

        original = numbered_text[start:end]
        lower = original.lower()
        erhua = ERHUA_MERGED_RE.fullmatch(lower)
        if erhua and lower not in {"er1", "er2", "er3", "er4", "er5", "r5"}:
            base, tone = erhua.groups()
            out_parts.append(f"{base}{tone} r5")
        else:
            out_parts.append(original)

        cursor = end

    out_parts.append(numbered_text[cursor:])
    return "".join(out_parts)


def _pinyin_cc_cedict(word: str, pinyin_numbered: str) -> str:
    """
    Build a CC-CEDICT-normalized numbered pinyin string.

    This keeps "不" as bu4 and "一" as yi1 by Hanzi position while preserving
    the original separators (spaces, slashes).
    """
    cc_cedict = pinyin_numbered
    hanzi_chars = _extract_hanzi_chars(word)
    if not hanzi_chars:
        return _split_erhua_syllables(cc_cedict)
    if "不" not in hanzi_chars and "一" not in hanzi_chars:
        return _split_erhua_syllables(cc_cedict)

    syllable_matches = list(NUMBERED_SYLLABLE_RE.finditer(cc_cedict.lower()))
    if not syllable_matches:
        return _split_erhua_syllables(cc_cedict)

    # Map each Hanzi to the syllable index it most likely aligns with.
    # Handle erhua forms where "儿" may be merged into a preceding syllable (e.g., dianr3).
    char_to_syllable: List[int | None] = []
    syllable_idx = 0
    for idx, hanzi in enumerate(hanzi_chars):
        is_suffix_erhua = hanzi == "儿" and idx > 0 and syllable_idx > 0
        if is_suffix_erhua:
            char_to_syllable.append(syllable_idx - 1)
            continue
        if syllable_idx >= len(syllable_matches):
            char_to_syllable.append(None)
            continue
        char_to_syllable.append(syllable_idx)
        syllable_idx += 1

    override_indices: dict[int, str] = {}
    used_override_indices: set[int] = set()
    for char_idx, hanzi in enumerate(hanzi_chars):
        override = CC_CEDICT_TONE_OVERRIDES.get(hanzi)
        if not override:
            continue

        target_prefix = override[:-1]
        preferred_idx = char_to_syllable[char_idx]
        chosen_idx: int | None = None

        if preferred_idx is not None and preferred_idx < len(syllable_matches):
            preferred_syllable = syllable_matches[preferred_idx].group(0)[:-1]
            if preferred_syllable.startswith(target_prefix):
                chosen_idx = preferred_idx

        if chosen_idx is None:
            for syll_idx, match in enumerate(syllable_matches):
                if syll_idx in used_override_indices:
                    continue
                if match.group(0)[:-1].startswith(target_prefix):
                    chosen_idx = syll_idx
                    break

        if chosen_idx is None and preferred_idx is not None and preferred_idx < len(syllable_matches):
            chosen_idx = preferred_idx

        if chosen_idx is not None:
            override_indices[chosen_idx] = override
            used_override_indices.add(chosen_idx)

    out_parts: List[str] = []
    cursor = 0
    for idx, match in enumerate(syllable_matches):
        out_parts.append(cc_cedict[cursor:match.start()])
        override = override_indices.get(idx)
        out_parts.append(override if override else match.group(0))
        cursor = match.end()

    out_parts.append(cc_cedict[cursor:])
    cc_cedict = "".join(out_parts)
    return _split_erhua_syllables(cc_cedict)


def _validate_pinyin_text(pinyin: str, word_index: str) -> None:
    """Validate pinyin symbols and syllables for one row."""
    normalized = unicodedata.normalize("NFC", pinyin).lower()
    for ch in normalized:
        if ch.isspace() or ch in PINYIN_ALLOWED_SEPARATORS:
            continue
        if ch in TONE_MARKS:
            continue
        if ch == "ü" or ("a" <= ch <= "z"):
            continue
        raise ValueError(
            f"Unsupported pinyin character '{ch}' for word index {word_index}. "
            f"Allowed separator exceptions: {sorted(PINYIN_EXCEPTION_CHARS)}."
        )

    tokens = _tokenize_pinyin(normalized)
    if not tokens:
        raise ValueError(f"Empty pinyin for word index {word_index}.")

    has_syllable = False
    for token, is_separator in tokens:
        if is_separator:
            continue
        has_syllable = True
        base = _strip_tone_marks(token)
        _segment_syllables(base)

    if not has_syllable:
        raise ValueError(f"No syllables found in pinyin '{pinyin}' for word index {word_index}.")


def validate_rows(rows: Sequence[Row]) -> None:
    """Validate parsed rows against output schema rules."""
    max_shown_errors = 25
    shown_errors: List[str] = []
    total_errors = 0

    for row_num, row in enumerate(rows, start=1):
        if not row.word_index.isdigit():
            total_errors += 1
            if len(shown_errors) < max_shown_errors:
                shown_errors.append(f"Row {row_num}: invalid word_index '{row.word_index}'.")

        if row.level not in VALID_HSK_LEVELS:
            total_errors += 1
            if len(shown_errors) < max_shown_errors:
                shown_errors.append(
                    f"Row {row_num} (word_index {row.word_index}): invalid level '{row.level}'."
                )

        if not WORD_VALID_RE.fullmatch(row.word):
            total_errors += 1
            if len(shown_errors) < max_shown_errors:
                shown_errors.append(
                    f"Row {row_num} (word_index {row.word_index}): "
                    f"invalid word '{row.word}' "
                    "(must be CJK characters, optionally ending with 1 or 2)."
                )

        try:
            _validate_pinyin_text(row.pinyin, row.word_index)
            expected_numbered = _pinyin_numbered(row.pinyin, row.word_index)
        except ValueError as exc:
            total_errors += 1
            if len(shown_errors) < max_shown_errors:
                shown_errors.append(
                    f"Row {row_num} (word_index {row.word_index}): invalid pinyin "
                    f"'{row.pinyin}' ({exc})."
                )
            continue

        if row.pinyin_numbered != expected_numbered:
            total_errors += 1
            if len(shown_errors) < max_shown_errors:
                shown_errors.append(
                    f"Row {row_num} (word_index {row.word_index}): pinyin_numbered mismatch "
                    f"(found '{row.pinyin_numbered}', expected '{expected_numbered}')."
                )

        expected_cc_cedict = _pinyin_cc_cedict(row.word, expected_numbered)
        if row.pinyin_cc_cedict != expected_cc_cedict:
            total_errors += 1
            if len(shown_errors) < max_shown_errors:
                shown_errors.append(
                    f"Row {row_num} (word_index {row.word_index}): pinyin_cc-cedict mismatch "
                    f"(found '{row.pinyin_cc_cedict}', expected '{expected_cc_cedict}')."
                )

    if total_errors:
        details = "\n".join(f"- {msg}" for msg in shown_errors)
        remaining = total_errors - len(shown_errors)
        remaining_line = (
            f"\n- ... and {remaining} more validation error(s)." if remaining > 0 else ""
        )
        raise ValueError(f"Validation failed with {total_errors} error(s):\n{details}{remaining_line}")


def _is_pinyin_token(token: str) -> bool:
    """Return True if a whitespace-delimited token looks like pinyin."""
    if not token or CJK_RE.search(token):
        return False
    stripped = "".join(ch for ch in token if ch not in SEPARATOR_CHARS)
    return bool(stripped) and bool(PINYIN_TOKEN_RE.fullmatch(stripped))


@dataclasses.dataclass(frozen=True)
class Row:
    """A single TSV row."""

    word_index: str
    level: str
    word: str
    pinyin: str
    pinyin_numbered: str
    pinyin_cc_cedict: str
    part_of_speech: str

    def to_tsv(self) -> str:
        """Serialize the row to a TSV line."""
        return "\t".join(
            [
                self.word_index,
                self.level,
                self.word,
                self.pinyin,
                self.pinyin_numbered,
                self.pinyin_cc_cedict,
                self.part_of_speech,
            ]
        )


@dataclasses.dataclass(frozen=True)
class PendingEntry:
    """Entry awaiting a trailing Hanzi line due to PDF extraction order."""

    word_index: str
    level_field: str
    pinyin: str
    part_of_speech: str


def extract_text_lines(
    pdf_path: Path,
    page_start: int | None,
    page_end: int | None,
) -> Iterator[str]:
    """
    Yield text lines from a PDF.

    Args:
        pdf_path: Input PDF file.
        page_start: 1-based start page, inclusive. None means first page.
        page_end: 1-based end page, inclusive. None means last page.
    """
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        start_idx = 0 if page_start is None else max(page_start - 1, 0)
        end_idx = total_pages - 1 if page_end is None else min(page_end - 1, total_pages - 1)

        for page_idx in range(start_idx, end_idx + 1):
            text = pdf.pages[page_idx].extract_text(x_tolerance=1, y_tolerance=1)
            if not text:
                continue
            for line in text.splitlines():
                yield line.strip()


def parse_levels(level_field: str) -> List[str]:
    """
    Parse a level field into a list of level labels.

    Examples:
        "1" -> ["1"]
        "1（4）" -> ["1", "4"]
        "3（4）（7-9）" -> ["3", "4", "7-9"]
    """
    if "（" in level_field:
        base = level_field.split("（", 1)[0].strip()
        extras = re.findall(r"（([^）]+)）", level_field)
        levels = [lvl for lvl in [base] + [e.strip() for e in extras] if lvl]
        return levels if levels else [level_field.strip()]
    return [level_field.strip()]


def split_pos_groups(pos_field: str) -> List[str]:
    """
    Split the part-of-speech field into groups, keeping parenthesized groups intact.

    This function returns a list where the first element corresponds to the base level,
    and subsequent elements correspond to parenthesized groups in order of appearance.
    """
    pos_field = pos_field.strip()
    if not pos_field:
        return [""]

    groups: List[str] = []
    buf: List[str] = []
    depth = 0
    for ch in pos_field:
        if ch == "（":
            depth += 1
        elif ch == "）":
            depth = max(depth - 1, 0)

        if ch == "、" and depth == 0:
            groups.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)

    if buf:
        groups.append("".join(buf).strip())

    base_parts: List[str] = []
    paren_groups: List[str] = []
    for group in groups:
        if group.startswith("（") and group.endswith("）"):
            paren_groups.append(group[1:-1].strip())
        elif group:
            base_parts.append(group)

    base = "、".join(base_parts).strip()
    out: List[str] = []
    if base or not paren_groups:
        out.append(base)
    else:
        out.append("")
    out.extend(paren_groups)
    return out


def _strip_tone_marks(syllable: str) -> str:
    """Strip tone marks and normalize separators to get base pinyin letters."""
    chars: List[str] = []
    for ch in syllable:
        if ch in TONE_MARKS:
            chars.append(TONE_MARKS[ch][0])
        elif ch.lower() == "v":
            chars.append("ü")
        else:
            chars.append(ch)
    return "".join(chars).lower()


def _tokenize_pinyin(pinyin: str) -> List[Tuple[str, bool]]:
    """Split pinyin into chunks and separators.

    Returns a list of (token, is_separator) tuples.
    """
    tokens: List[Tuple[str, bool]] = []
    buf: List[str] = []

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


def _collect_valid_syllables() -> List[str]:
    """Build a list of valid pinyin syllables from pypinyin dictionaries."""
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


def _segment_syllables(base: str) -> List[Tuple[int, int, str]]:
    """Segment a base pinyin string into valid syllables.

    Returns:
        A list of (start_index, end_index, syllable_base) tuples.
    """
    if not base:
        return []

    memo: dict[int, List[Tuple[int, int, str]] | None] = {}

    def helper(idx: int) -> List[Tuple[int, int, str]] | None:
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


def _pinyin_numbered(pinyin: str, word_index: str) -> str:
    """Convert tone-marked pinyin into numbered pinyin with syllable spacing."""
    pinyin = unicodedata.normalize("NFC", pinyin)
    pinyin = pinyin.lower()
    tokens = _tokenize_pinyin(pinyin)
    if not tokens:
        raise ValueError(f"Empty pinyin for word index {word_index}.")

    numbered_syllables: List[str] = []
    normalized_parts: List[str] = []
    output_parts: List[str] = []

    for token, is_separator in tokens:
        if is_separator:
            output_parts.append(token)
            continue

        chunk = token
        base_chars: List[str] = []
        tone_marks: List[int] = []
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

        chunk_syllables: List[str] = []
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
            raise ValueError(
                f"Invalid syllable '{syllable}' for word index {word_index}."
            )

    output = ""
    for part in output_parts:
        if part in PRESERVE_SEPARATORS:
            output = output.rstrip() + part
            continue
        if output and not output.endswith((" ",) + tuple(PRESERVE_SEPARATORS)):
            output += " "
        output += part

    return output.strip()


def _build_rows(
    word_index: str,
    level_field: str,
    word: str,
    pinyin: str,
    part_of_speech: str,
) -> List[Row]:
    """Build rows for a single word entry."""
    pinyin_numbered = _pinyin_numbered(pinyin, word_index)
    pinyin_cc_cedict = _pinyin_cc_cedict(word, pinyin_numbered)

    levels = parse_levels(level_field)
    if len(levels) == 1:
        return [
            Row(
                word_index=word_index,
                level=levels[0],
                word=word,
                pinyin=pinyin,
                pinyin_numbered=pinyin_numbered,
                pinyin_cc_cedict=pinyin_cc_cedict,
                part_of_speech=part_of_speech,
            )
        ]

    pos_groups = split_pos_groups(part_of_speech)
    if len(pos_groups) != len(levels):
        pos_groups = [part_of_speech] * len(levels)

    return [
        Row(
            word_index=word_index,
            level=level,
            word=word,
            pinyin=pinyin,
            pinyin_numbered=pinyin_numbered,
            pinyin_cc_cedict=pinyin_cc_cedict,
            part_of_speech=pos_group,
        )
        for level, pos_group in zip(levels, pos_groups)
    ]


def parse_entries(lines: Iterable[str]) -> List[Row]:
    """Parse all entry lines into rows."""
    rows: List[Row] = []
    pending: PendingEntry | None = None

    for line in lines:
        line = _replace_cid_tokens(line)
        if not line or line.startswith("序号"):
            continue

        if pending:
            if CJK_ONLY_RE.fullmatch(line):
                if line in PAGE_MARKERS:
                    continue
                rows.extend(
                    _build_rows(
                        pending.word_index,
                        pending.level_field,
                        line,
                        pending.pinyin,
                        pending.part_of_speech,
                    )
                )
                pending = None
                continue
            raise ValueError(
                f"Missing trailing word for index {pending.word_index}. "
                "Update overrides or extraction settings."
            )

        match = ENTRY_RE.match(line)
        if not match:
            continue

        word_index, level_field, rest = match.groups()
        parts = rest.split()
        if len(parts) < 2:
            continue

        word = parts[0]
        remaining = parts[1:]
        first_token = remaining[0]

        if _is_pinyin_token(word) and CJK_RE.search(first_token):
            part_of_speech = " ".join(remaining).strip()
            override_word = MISSING_WORD_OVERRIDES.get(word_index)
            if override_word:
                rows.extend(
                    _build_rows(
                        word_index,
                        level_field,
                        override_word,
                        word,
                        part_of_speech,
                    )
                )
            else:
                pending = PendingEntry(
                    word_index=word_index,
                    level_field=level_field,
                    pinyin=word,
                    part_of_speech=part_of_speech,
                )
            continue

        pinyin_parts: List[str] = []
        split_idx = 0
        for idx, token in enumerate(remaining):
            if _is_pinyin_token(token):
                pinyin_parts.append(token)
                split_idx = idx + 1
            else:
                break

        if not pinyin_parts:
            pinyin_parts = [first_token]
            split_idx = 1

        pinyin = "".join(pinyin_parts)
        part_of_speech = " ".join(remaining[split_idx:]).strip()

        rows.extend(_build_rows(word_index, level_field, word, pinyin, part_of_speech))

    if pending:
        raise ValueError(
            f"Missing trailing word for index {pending.word_index}. "
            "Update overrides or extraction settings."
        )
    return rows


def write_tsv(rows: Sequence[Row], output_path: Path, include_header: bool) -> None:
    """Write rows to a TSV file."""
    with output_path.open("w", encoding="utf-8") as handle:
        if include_header:
            handle.write(
                "word_index\tlevel\tword\tpinyin\tpinyin_numbered\tpinyin_cc-cedict\tpart_of_speech\n"
            )
        for row in rows:
            handle.write(row.to_tsv())
            handle.write("\n")


def _missing_word_indexes(rows: Sequence[Row]) -> List[int]:
    """Return missing numeric word indexes in the observed index range."""
    if not rows:
        return []

    indexes = sorted({int(row.word_index) for row in rows})
    start = indexes[0]
    end = indexes[-1]
    observed = set(indexes)
    return [idx for idx in range(start, end + 1) if idx not in observed]


def _format_integer_ranges(values: Sequence[int]) -> str:
    """Format sorted integers as compact ranges (e.g. 3-5, 8, 10-12)."""
    if not values:
        return ""

    ranges: List[str] = []
    start = values[0]
    prev = values[0]

    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = value
        prev = value

    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(ranges)


def _format_table(headers: Sequence[str], data_rows: Sequence[Sequence[str]]) -> str:
    """Format rows as an ASCII table for terminal output."""
    widths = [len(header) for header in headers]
    for row in data_rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    header_line = " | ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers))
    separator_line = "-+-".join("-" * width for width in widths)
    body_lines = [
        " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(row))
        for row in data_rows
    ]
    return "\n".join([header_line, separator_line, *body_lines])


def _collect_pos_counts(rows: Sequence[Row]) -> Counter[str]:
    """Count each part-of-speech token from parsed rows."""
    counts: Counter[str] = Counter()
    for row in rows:
        part_of_speech = row.part_of_speech.strip()
        if not part_of_speech:
            continue
        for token in part_of_speech.split("、"):
            token = token.strip()
            if token:
                counts[token] += 1
    return counts


def _level_sort_key(level: str) -> Tuple[int, str]:
    """Sort levels by leading number, then by full label."""
    match = re.match(r"^(\d+)", level)
    leading = int(match.group(1)) if match else 10**9
    return leading, level


def print_output_analysis(rows: Sequence[Row]) -> None:
    """Print continuity checks and output summaries after TSV generation."""
    if not rows:
        print("No rows parsed; skipping output analysis.")
        return

    indexes = sorted({int(row.word_index) for row in rows})
    missing_indexes = _missing_word_indexes(rows)
    if missing_indexes:
        print(
            "WARNING: Missing word_index values "
            f"({len(missing_indexes)}): {_format_integer_ranges(missing_indexes)}"
        )
    else:
        print(
            "word_index continuity check: no missing values "
            f"(range {indexes[0]}-{indexes[-1]})."
        )

    pos_counts = _collect_pos_counts(rows)
    pos_rows = [
        [token, str(count)]
        for token, count in sorted(
            pos_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    print("\nPart-of-speech tokens in output TSV:")
    print(_format_table(["part_of_speech", "count"], pos_rows))

    level_counts: Counter[str] = Counter()
    for row in rows:
        level_counts[row.level] += 1

    level_rows = [
        [level, str(level_counts[level])]
        for level in sorted(level_counts, key=_level_sort_key)
    ]
    print("\nWord rows by HSK level:")
    print(_format_table(["level", "word_count"], level_rows))


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Extract an HSK word list from a PDF into a TSV file."
        )
    )
    parser.add_argument(
        "--pdf",
        required=True,
        type=Path,
        help="Path to the input PDF containing the word list.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output TSV path.",
    )
    parser.add_argument(
        "--page-start",
        type=int,
        default=1,
        help=(
            "1-based start page (inclusive). Default: 1 (first page)."
        ),
    )
    parser.add_argument(
        "--page-end",
        type=int,
        default=None,
        help=(
            "1-based end page (inclusive). Default: last page."
        ),
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="Do not write the TSV header row.",
    )
    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_arg_parser()
    args = parser.parse_args()

    if not args.pdf.exists():
        raise SystemExit(f"PDF not found: {args.pdf}")

    lines = extract_text_lines(args.pdf, args.page_start, args.page_end)
    rows = parse_entries(lines)
    validate_rows(rows)
    write_tsv(rows, args.output, include_header=not args.no_header)

    print(f"Wrote {len(rows)} rows to {args.output}")
    print_output_analysis(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
