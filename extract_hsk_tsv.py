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
- Pinyin is split into syllables, tone numbers are derived from accent marks, and
  neutral tone syllables use tone 5.
- Slash separators are preserved in the numbered output to reflect alternate readings.
- Other separator symbols (including dashes) are treated as syllable boundaries and removed.
- Syllabic interjections (e.g., "ng") are supported and treated as valid syllables.
- A small override table fixes known PDF extraction gaps where the Hanzi is missing.

Some source PDFs are extracts from a larger book; if your word list starts later in the
book (e.g., pages 4-278 of the original), use --page-start/--page-end to match that range.
"""

from __future__ import annotations

import argparse
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

MISSING_WORD_OVERRIDES = {
    "1726": "提",
    "1844": "盐",
    "2092": "藏",
    "2785": "某",
    "10550": "盏",
}
LETTER_PATTERN = re.compile(r"[a-zü]+")


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

    levels = parse_levels(level_field)
    if len(levels) == 1:
        return [
            Row(
                word_index=word_index,
                level=levels[0],
                word=word,
                pinyin=pinyin,
                pinyin_numbered=pinyin_numbered,
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
            part_of_speech=pos_group,
        )
        for level, pos_group in zip(levels, pos_groups)
    ]


def parse_entries(lines: Iterable[str]) -> List[Row]:
    """Parse all entry lines into rows."""
    rows: List[Row] = []
    pending: PendingEntry | None = None

    for line in lines:
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
            handle.write("word_index\tlevel\tword\tpinyin\tpinyin_numbered\tpart_of_speech\n")
        for row in rows:
            handle.write(row.to_tsv())
            handle.write("\n")


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
    write_tsv(rows, args.output, include_header=not args.no_header)

    print(f"Wrote {len(rows)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
