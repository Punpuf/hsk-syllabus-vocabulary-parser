# HSK 3.0 (2026) Word List TSV Extractor

This module extracts the **HSK 3.0 (2026)** vocabulary list into a clean TSV. The HSK 3.0 list was released in **November 2025** and is scheduled to be implemented in **July 2026**.

## Input Source

The expected input is the official syllabus:
- **Syllabus for the Chinese Proficiency Test**
- Download: [新版HSK考试大纲（词汇、汉字、语法）](https://hsk.cn-bj.ufileos.com/3.0/%E6%96%B0%E7%89%88HSK%E8%80%83%E8%AF%95%E5%A4%A7%E7%BA%B2%EF%BC%88%E8%AF%8D%E6%B1%87%E3%80%81%E6%B1%89%E5%AD%97%E3%80%81%E8%AF%AD%E6%B3%95%EF%BC%89.pdf)

## Goal

The goal of this project is to produce a **clean list of Chinese words** where **both Hanzi and pinyin are present**. Many existing lists only store Hanzi, which is not sufficient for uniquely identifying a word because multiple words can share the same Hanzi with different pronunciations.

## AI Usage Notice

A model was used to generate the processing script and this README file.

## Output Quality

A manual check was performed by comparing 20 pages of the original syllabus with the output of the script, and the information matched. Further quality analysis is recommended. If you identify any problems, please open an issue.

## How To Use

```bash
uv run python extract_hsk_tsv.py \
  --pdf "新版HSK考试大纲（词汇、汉字、语法）.pdf" \
  --output "hsk_word_list.tsv" \
  --page-start 4 \
  --page-end 278
```

Optional page controls:
- `--page-start` (1-based, inclusive)
- `--page-end` (1-based, inclusive)

## Processing Rules

The input lines in the syllabus follow this structure:
- `word_index`
- `level`
- `word`
- `pinyin`
- `part_of_speech`

If a word appears in multiple levels, the syllabus uses parentheses in both the `level` and `part_of_speech` columns. For example:
- `level`: `1（4）`
- `part_of_speech`: `形、介、（动、量）`

In those cases, the extractor **creates multiple entries**, one per level, repeating the same word index and other fields with the corresponding part-of-speech group.

## Pinyin Numbering

The extractor adds a `pinyin_numbered` column. 

### The Process

1. Normalize and lowercase the pinyin.
2. Split into chunks on separators and whitespace.
3. Segment each chunk into valid pinyin syllables.
4. Derive tone numbers from accent marks (neutral tone = `5`).
5. Preserve `/` to indicate alternate readings (`shéi/shuí` and `shú/shóu`).
6. Remove other separators (e.g., `-`, `’`).
7. Validate that rejoining the numbered syllables (without numbers/spaces) matches the normalized pinyin.

### Edge Cases and Fixes

- **Syllabic interjections**: syllables like `ng` are not in standard syllable lists, so the validator allows `m`, `n`, `ng`, `hm`, `hng`.
- **Uppercase accented pinyin**: normalized to lowercase before segmentation (e.g., `Ōuzhōu`).
- **PDF extraction order issues**: some lines contain pinyin before Hanzi. The extractor buffers these and attaches the next Hanzi-only line. Page marker artifacts like `汉/国/际/考` are ignored while waiting.
- **Missing Hanzi in extraction**: a small override table patches known missing Hanzi cases where the PDF layout drops the word.
