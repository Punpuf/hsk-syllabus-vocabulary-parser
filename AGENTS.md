# AGENTS.md

## Project Overview

This repository extracts the official HSK 3.0 vocabulary list from a syllabus PDF into TSV,
then enriches rows with CC-CEDICT pinyin and definitions.

Pipeline stages:
1. Stage 1: PDF parsing to raw rows
2. Stage 2: numbered pinyin generation
3. Stage 3: CC-CEDICT enrichment
4. Stage 4: validation and continuity checks
5. Stage 5: TSV + Markdown report export

Main package layout:
- CLI: `src/hsk_pipeline/cli.py`
- Orchestration: `src/hsk_pipeline/pipeline.py`
- Stages: `src/hsk_pipeline/stages/`
- CEDICT utilities: `src/hsk_pipeline/cedict/`
- Validation: `src/hsk_pipeline/validation.py`
- Report builder: `src/hsk_pipeline/reporting/report_md.py`

Primary data files:
- Main dictionary: `cedict_ts.u8`
- Disambiguation map: `data/disambiguation.tsv`
- Patch dictionary: `data/cedict_patch.u8`

Primary outputs:
- TSV (default example): `hsk_word_list.tsv`
- Markdown report (default): `report.md` next to TSV output

## Build And Run Commands

Use `uv` with project root as working directory.

1. Install dependencies:
```bash
uv sync --group dev
```

2. Run extractor pipeline:
```bash
uv run python -m hsk_pipeline.cli \
  --pdf "新版HSK考试大纲（词汇、汉字、语法）.pdf" \
  --output "hsk_word_list.tsv" \
  --page-start 4 \
  --page-end 278
```

3. Allow unresolved Stage 3 rows (temporary/debug mode):
```bash
uv run python -m hsk_pipeline.cli \
  --pdf "新版HSK考试大纲（词汇、汉字、语法）.pdf" \
  --output "hsk_word_list.tsv" \
  --page-start 4 \
  --page-end 278 \
  --allow-unresolved
```

4. Optional quick checks:
```bash
head -n 10 hsk_word_list.tsv
rg -n "^14\t|^24\t|^120\t" hsk_word_list.tsv
```

## Testing Instructions

Automated tests are available.

1. Run unit + integration tests:
```bash
uv run --with pytest pytest
```

2. Format checks:
```bash
uv run --with black black src tests
```

3. Recommended end-to-end verification:
- Run pipeline command on pages `4-278`.
- Confirm terminal output includes:
  - `Wrote ... rows to ...`
  - `Wrote report to ...`
  - continuity message and POS/level tables
  - resolution summary line

Current Stage 1/2 parity expectation for official pages (`4-278`):
- 11,105 rows
- `word_index` range `1-11000` with no missing indexes

## Code Style Guidelines

- Target Python 3.10+.
- Keep changes minimal and scoped.
- Prefer explicit logic over implicit behavior.
- Keep Unicode handling intact (Hanzi + tone-marked pinyin).
- Use dataclasses/type hints consistently.
- Keep markdown docs current when behavior or schema changes.

## Security Considerations

- Treat input PDFs as untrusted files.
- Avoid network-dependent runtime logic in extraction/enrichment.
- Do not hardcode machine-specific absolute paths.
- Avoid unnecessary regeneration of large outputs when docs-only changes are made.

## Data And Parsing Gotchas

- Source pinyin may include internal spaces; source `pinyin` output keeps row value from Stage 1 parsing.
- Multiple pinyin pronunciations use `/`.
- Multiple POS values use `、`.
- Some words use sense suffixes (`1`, `2`) in `word`; Stage 3 strips non-Hanzi for dictionary lookup but preserves original output word.
- Multi-level mappings split one source row into multiple TSV rows.
- Default Stage 3 policy is hard-fail on unresolved matches unless `--allow-unresolved` is set.

## Commit And PR Guidelines

- Prefer Conventional Commit style: `feat: ...`, `fix: ...`, `docs: ...`, `refactor: ...`, `chore: ...`.
- Include a body description with bullet points
- Keep commits scoped to related behavior/files.
- In PR verification notes, include:
  - exact command(s) run
  - row count + continuity result
  - resolution summary (including unresolved count)
  - reason output artifacts changed
- Do not bundle unrelated workspace changes in the same commit.
