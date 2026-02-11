"""Stage 1: Extract and normalize raw rows from the syllabus PDF.

The module parses line-oriented PDF text and outputs ``RawRow`` entries containing
``word_index``, ``level``, ``word``, ``pinyin``, and ``part_of_speech``.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Iterable, Iterator

import pdfplumber

from hsk_pipeline.models import RawRow

ENTRY_RE = re.compile(r"^(\d+)\s+(\S+)\s+(.+)$")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
CJK_ONLY_RE = re.compile(r"[\u4e00-\u9fff]+")
PAGE_MARKERS = {"汉", "国", "际", "考"}
CID_PATTERN = re.compile(r"\(cid:(\d+)\)")
PINYIN_TOKEN_RE = re.compile(r"^[A-Za-zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜńňǹḿüÜêÊ]+$")
SEPARATOR_CHARS = set("-/'’·•")

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


@dataclass(frozen=True)
class PendingEntry:
    """Temporary state for entries whose Hanzi appears on the next line.

    Some PDF extraction artifacts place pinyin where the Hanzi word should be,
    followed by a Hanzi-only line. This structure stores the parsed values while
    waiting for the trailing Hanzi line to complete a row.
    """

    word_index: str
    level_field: str
    pinyin: str
    part_of_speech: str


def _replace_cid_tokens(text: str) -> str:
    """Replace ``(cid:NNNN)`` placeholders with mapped Hanzi when known.

    The extractor occasionally emits CID placeholders instead of glyphs. This
    function performs deterministic text substitution using a fixed mapping table
    to recover expected Hanzi characters before parsing entry structure.

    Args:
        text: Raw text line as extracted from ``pdfplumber``.

    Returns:
        The line with known CID placeholders replaced; unknown placeholders are
        left unchanged to avoid accidental corruption.
    """

    def repl(match: re.Match[str]) -> str:
        cid = match.group(1)
        return CID_CHAR_MAP.get(cid, match.group(0))

    return CID_PATTERN.sub(repl, text)


def _is_pinyin_token(token: str) -> bool:
    """Determine whether a whitespace token resembles pinyin text.

    The parser uses this classifier to decide where pinyin ends and part-of-
    speech begins. Hanzi-containing tokens are rejected, and separator symbols
    are ignored during validation so forms like ``shéi/shuí`` remain valid.

    Args:
        token: Whitespace-delimited token from an entry line.

    Returns:
        ``True`` if the token matches supported pinyin character inventory after
        stripping separator symbols; otherwise ``False``.
    """

    if not token or CJK_RE.search(token):
        return False
    stripped = "".join(ch for ch in token if ch not in SEPARATOR_CHARS)
    return bool(stripped) and bool(PINYIN_TOKEN_RE.fullmatch(stripped))


def extract_text_lines(
    pdf_path: Path,
    page_start: int | None,
    page_end: int | None,
) -> Iterator[str]:
    """Yield trimmed text lines from selected pages of a PDF.

    The function opens the PDF once, converts one page at a time to plain text,
    and yields individual stripped lines. Page boundaries are inclusive and
    1-based to match human page references used in CLI arguments.

    Args:
        pdf_path: Path to the source syllabus PDF.
        page_start: 1-based start page, inclusive; ``None`` means first page.
        page_end: 1-based end page, inclusive; ``None`` means last page.

    Yields:
        Non-empty page text lines with leading/trailing whitespace removed.
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


def parse_levels(level_field: str) -> list[str]:
    """Expand a level field into concrete level labels.

    Source level fields may include extra levels inside full-width parentheses,
    such as ``1（4）`` or ``3（4）（7-9）``. This function normalizes these into
    an ordered list where the first item is the base level followed by extras.

    Args:
        level_field: Raw level text captured from the source line.

    Returns:
        Ordered level labels to emit for the entry.
    """

    if "（" in level_field:
        base = level_field.split("（", 1)[0].strip()
        extras = re.findall(r"（([^）]+)）", level_field)
        levels = [lvl for lvl in [base] + [e.strip() for e in extras] if lvl]
        return levels if levels else [level_field.strip()]
    return [level_field.strip()]


def split_pos_groups(pos_field: str) -> list[str]:
    """Split part-of-speech groups while preserving parenthesized bundles.

    The source POS column uses ``、`` as a delimiter, but parenthesized groups
    map to extra levels and must stay intact. This parser performs a balanced
    scan over full-width parentheses and returns one base group plus zero or
    more extra groups in appearance order.

    Args:
        pos_field: Raw part-of-speech text from the source line.

    Returns:
        POS groups aligned with the level list returned by :func:`parse_levels`.
    """

    pos_field = pos_field.strip()
    if not pos_field:
        return [""]

    groups: list[str] = []
    buf: list[str] = []
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

    base_parts: list[str] = []
    paren_groups: list[str] = []
    for group in groups:
        if group.startswith("（") and group.endswith("）"):
            paren_groups.append(group[1:-1].strip())
        elif group:
            base_parts.append(group)

    base = "、".join(base_parts).strip()
    out: list[str] = []
    if base or not paren_groups:
        out.append(base)
    else:
        out.append("")
    out.extend(paren_groups)
    return out


def _build_raw_rows(
    word_index: str,
    level_field: str,
    word: str,
    pinyin: str,
    part_of_speech: str,
) -> list[RawRow]:
    """Create one or more ``RawRow`` objects for a parsed entry.

    Multi-level entries expand into multiple rows while reusing the same source
    values. POS groups are aligned with levels using ``split_pos_groups``; when
    alignment fails, the original POS string is replicated across all levels.

    Args:
        word_index: Source word index field.
        level_field: Source level field that may contain extra levels.
        word: Hanzi term.
        pinyin: Source pinyin text.
        part_of_speech: Source part-of-speech text.

    Returns:
        A list of ``RawRow`` instances representing expanded level mappings.
    """

    levels = parse_levels(level_field)
    if len(levels) == 1:
        return [
            RawRow(
                word_index=word_index,
                level=levels[0],
                word=word,
                pinyin=pinyin,
                part_of_speech=part_of_speech,
            )
        ]

    pos_groups = split_pos_groups(part_of_speech)
    if len(pos_groups) != len(levels):
        pos_groups = [part_of_speech] * len(levels)

    return [
        RawRow(
            word_index=word_index,
            level=level,
            word=word,
            pinyin=pinyin,
            part_of_speech=pos_group,
        )
        for level, pos_group in zip(levels, pos_groups)
    ]


def parse_entries(lines: Iterable[str]) -> list[RawRow]:
    """Parse Stage 1 rows from extracted PDF lines.

    The parser skips headers/noise, handles known extraction artifacts where a
    pinyin token appears before a delayed Hanzi line, and expands multi-level
    rows into separate records with aligned POS fields.

    Args:
        lines: Pre-trimmed text lines, typically produced by
            :func:`extract_text_lines`.

    Returns:
        Parsed Stage 1 rows in source order.

    Raises:
        ValueError: If a delayed Hanzi line is expected but not found.
    """

    rows: list[RawRow] = []
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
                    _build_raw_rows(
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
                    _build_raw_rows(
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

        pinyin_parts: list[str] = []
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

        rows.extend(_build_raw_rows(word_index, level_field, word, pinyin, part_of_speech))

    if pending:
        raise ValueError(
            f"Missing trailing word for index {pending.word_index}. "
            "Update overrides or extraction settings."
        )
    return rows


def extract_raw_rows(pdf_path: Path, page_start: int, page_end: int | None) -> list[RawRow]:
    """Run Stage 1 end-to-end extraction for a PDF page range.

    This convenience wrapper wires together line extraction and entry parsing for
    the CLI/pipeline orchestrator so Stage 1 has a single callable interface.

    Args:
        pdf_path: Path to source syllabus PDF.
        page_start: 1-based inclusive starting page.
        page_end: 1-based inclusive ending page, or ``None`` for last page.

    Returns:
        Parsed ``RawRow`` objects ready for Stage 2 numbering.
    """

    lines = extract_text_lines(pdf_path=pdf_path, page_start=page_start, page_end=page_end)
    return parse_entries(lines)
