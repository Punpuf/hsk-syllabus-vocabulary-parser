# AGENTS.md

## Project Overview

This repository extracts the official HSK 3.0 vocabulary list from a PDF syllabus into a TSV file.

- Main script: `extract_hsk_tsv.py`
- Main output: `hsk_word_list.tsv`
- Primary input PDF (example): `新版HSK考试大纲（词汇、汉字、语法）.pdf`
- Python package metadata: `pyproject.toml`

The script parses `word_index`, `level`, `word`, `pinyin`, and `part_of_speech`, generates `pinyin_numbered`, and prints post-run analysis (index continuity, POS counts, level counts).

## Build And Run Commands

Use `uv` with the project root as working directory.

1. Install dependencies:
```bash
uv sync
```

2. Run extractor:
```bash
uv run python extract_hsk_tsv.py \
  --pdf "新版HSK考试大纲（词汇、汉字、语法）.pdf" \
  --output "hsk_word_list.tsv" \
  --page-start 4 \
  --page-end 278
```

3. Optional quick checks:
```bash
head -n 10 hsk_word_list.tsv
rg -n "^14\t|^24\t|^120\t" hsk_word_list.tsv
```

## Testing Instructions

There is currently no dedicated automated test suite. Validate changes with repeatable script runs and output checks.

Recommended manual verification:

1. Run the extractor command above.
2. Confirm terminal output includes:
`Wrote ... rows to ...`, `word_index continuity check: ...`, and POS/level summary tables.
3. Confirm continuity warning behavior by inspecting output message when indexes are missing (if testing parser changes).
4. Spot-check a few known multi-sense and multi-level entries in `hsk_word_list.tsv`.

For the official syllabus pages (`4-278`), current expected output is:
- 11,105 TSV rows
- `word_index` range `1-11000` with no missing indexes

## Code Style Guidelines

- Target Python 3.10+.
- Keep changes minimal and focused; avoid broad refactors unless requested.
- Preserve existing function naming and typing style (`typing` hints and dataclasses are already used).
- Prefer explicit parsing logic over clever/implicit behavior.
- Keep Unicode handling intact (Hanzi and tone-marked pinyin are required).
- Update `README.md` when behavior/output format changes.

## Security Considerations

- Treat input PDFs as untrusted files. Do not execute or open unknown files outside the parser flow.
- Avoid adding network-dependent runtime behavior to extraction logic.
- Do not hardcode absolute machine-specific paths in code or docs.
- The source PDF and generated TSV are sizable and can impact diff readability and review time.
- Avoid unnecessary regeneration of `hsk_word_list.tsv` when changes are docs-only.

## Data And Parsing Gotchas

- Source pinyin may include internal spaces (for syllable/word boundaries); output `pinyin` normalizes these spaces away.
- Multiple pinyin pronunciations use `/`.
- Multiple POS values use `、`.
- Some words use sense suffixes (`1`, `2`) in `word` to distinguish same-Hanzi/same-pinyin senses.
- Multi-level mappings can split one source row into multiple TSV rows.

## Commit And PR Guidelines

- Prefer Conventional Commit style: `feat: ...`, `fix: ...`, `docs: ...`, `refactor: ...`, `chore: ...`.
- Keep commit messages scoped to actual changed files/behavior.
- Include a short verification note in PR descriptions with: command(s) run, key output summary (row count + continuity result), and why `hsk_word_list.tsv` changed (if applicable).
- Do not bundle unrelated workspace changes in the same commit.
