# HSK 3.0 (2026) Vocabulary Extraction Pipeline (PDF → TSV)

This project extracts the official **HSK 3.0 (2026)** vocabulary list from the syllabus PDF
and runs a staged enrichment pipeline:
- Stage 1: parse raw rows from PDF
- Stage 2: generate `pinyin_numbered`
- Stage 3: enrich from CC-CEDICT (`pinyin_cc-cedict`, `definition_cc-cedict`)
- Stage 4: validate rows and continuity
- Stage 5: export TSV + Markdown report

**Goal:** Produce a list of Chinese words per **HSK level** where **both Hanzi and pinyin** are present. Many existing HSK vocabulary lists only store Hanzi, which alone does not allow uniquely identifying a word because multiple words can share the same Hanzi with different pronunciations.

**Input Source:** 
- Syllabus for the Chinese Proficiency Test. 
- Download: [新版HSK考试大纲（词汇、汉字、语法）](https://hsk.cn-bj.ufileos.com/3.0/%E6%96%B0%E7%89%88HSK%E8%80%83%E8%AF%95%E5%A4%A7%E7%BA%B2%EF%BC%88%E8%AF%8D%E6%B1%87%E3%80%81%E6%B1%89%E5%AD%97%E3%80%81%E8%AF%AD%E6%B3%95%EF%BC%89.pdf)

**AI usage notice:** A model was used to generate the processing scripts and this README file.


## Output Structure

| word_index | level | word | pinyin    | part_of_speech | pinyin_numbered | pinyin_cc-cedict | definition_cc-cedict                   |
|------------|-------|------|-----------|----------------|-----------------|------------------|----------------------------------------|
| 1          | 1     | 爱    | ài        | 动              | ai4             | ai4              | to love; to be fond of; to like (..)   |
| 2          | 1     | 八    | bā        | 数              | ba1             | ba1              | eight                                  |
| 6          | 1     | 百    | bǎi       | 数              | bai3            | bai3             | hundred; numerous; all kinds of (..)   |
| 7          | 1     | 半    | bàn       | 数              | ban4            | ban4             | half; semi-; incomplete (..)           |
| 7          | 4     | 半    | bàn       | 副              | ban4            | ban4             | half; semi-; incomplete (..)           |
| 23         | 1     | 穿    | chuān     | 动              | chuan1          | chuan1           | to wear; to put on; to dress (..)      |
| 24         | 1     | 打电话  | dǎdiànhuà |                | da3 dian4 hua4  | da3 dian4 hua4   | to make a telephone call               |
| 33         | 1     | 点1   | diǎn      | 量              | dian3           | dian3            | to touch briefly; to tap; to mark (..) |
| 33         | 3     | 点1   | diǎn      | 名              | dian3           | dian3            | to touch briefly; to tap; to mark (..) |
| 336        | 2     | 点2   | diǎn      | 动              | dian3           | dian3            | to touch briefly; to tap; to mark (..) |
| 336        | 4     | 点2   | diǎn      | 名、量            | dian3           | dian3            | to touch briefly; to tap; to mark (..) |
| 3944       | 6     | 恶心   | ěxin      | 形、动            | e3 xin5         | e3 xin1          | nausea; to feel sick; disgust; (..)    |

## Output Quality

A manual (human-done) check was performed by comparing all entries on the first and last pages of the original syllabus with extracted output, and the information matched. Further quality analysis is very much recommended.

Each run also writes a Markdown quality report (`report.md` by default, next to the TSV) with:
- row counts by HSK level
- parts of speech token counts
- tone-insensitive unique matches
- tone-insensitive multi-candidate matches
- patch-resolved matches
- unresolved/no-match rows

If you identify any problems, please open an issue.

## How To Use

You can [download the generated TSV file](./hsk_word_list.tsv) directly, or if you want to run the script yourself, follow these steps:

1. Clone the project.
```bash
git clone git@github.com:Punpuf/hsk-syllabus-vocabulary-parser.git
cd hsk-syllabus-vocabulary-parser
```
2. Move the syllabus PDF to the project root.

3. Install `uv` (`pip install uv` or [visit the website for detailed instructions](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer)).

4. Run the extractor command.
```bash
uv run python -m hsk_pipeline.cli \
  --pdf "新版HSK考试大纲（词汇、汉字、语法）.pdf" \
  --output "hsk_word_list.tsv" \
  --page-start 4 \
  --page-end 278
```

By default, unresolved Stage 3 rows are a hard error.
To allow unresolved rows temporarily:

```bash
uv run python -m hsk_pipeline.cli \
  --pdf "新版HSK考试大纲（词汇、汉字、语法）.pdf" \
  --output "hsk_word_list.tsv" \
  --page-start 4 \
  --page-end 278 \
  --allow-unresolved
```

### Optional paths

- `--report`: defaults to `report.md` next to the TSV output
- `--cedict`: defaults to `cedict_ts.u8` (or `data/cedict_ts.u8` if present)
- `--disambiguation`: defaults to `data/disambiguation.tsv`
- `--patch`: defaults to `data/cedict_patch.u8`


### Tests

```bash
uv run --with pytest pytest
```

### Formatting

```bash
uv run --with black black src tests
```

## Project Layout

- `src/hsk_pipeline/cli.py`: CLI entrypoint
- `src/hsk_pipeline/pipeline.py`: stage orchestration
- `src/hsk_pipeline/stages/`: stage implementations
- `src/hsk_pipeline/cedict/`: CEDICT parser/repository/matching logic
- `src/hsk_pipeline/reporting/report_md.py`: markdown report generation
- `src/hsk_pipeline/io/tsv_io.py`: TSV writer
- `src/hsk_pipeline/validation.py`: stage/output validation
- `data/disambiguation.tsv`: tone-insensitive multi-match overrides
- `data/cedict_patch.u8`: CEDICT-format patch file

## Processing Rules

The source syllabus rows are interpreted as:
- `word_index`
- `level`
- `word`
- `pinyin`
- `part_of_speech`

<details>
<summary>Notes on the source syllabus formatting conventions.</summary>

**Conventions used in the syllabus:**
- Multiple pinyin pronunciations in `pinyin` are separated by `/` (e.g., `shéi/shuí`).
- Multiple part-of-speech labels in `part_of_speech` are separated by `、`.
- Some syllabus entries include internal pinyin spaces to show sub-word boundaries (e.g., `打电话` as `dǎ diànhuà`). In the extractor output, this internal space is removed in `pinyin` (output: `dǎdiànhuà`).

If a word appears in multiple levels, the syllabus uses parentheses in both the `level` and `part_of_speech` columns. For example:
- `level`: `1（4）`
- `part_of_speech`: `形、介、（动、量）`

In those cases, the extractor **creates multiple entries**, one per level, repeating the **same word index** (so it's easier to compare the script's result with the syllabus) and other fields with the corresponding part-of-speech group.

**Sense Suffixes in `word` (`1` / `2`)**

Some entries append `1` or `2` to the `word` field (for example, `点1`, `点2`, `等1`, `等2`).  
This marks different dictionary senses that share the same Hanzi and the same pinyin spelling.
There are no examples present of words with more than two senses in the syllabus.

Examples from the generated TSV (the _meanings_ in the table below are AI-generated and may very well be incorrect, this was included only to help illustrate):

| pair      | pinyin | `1` meaning + POS/level                       | `2` meaning + POS/level                                  |
|-----------|--------|-----------------------------------------------|----------------------------------------------------------|
| 会1 / 会2   | huì    | `会1`: *can / be able to* (verb, level 1)      | `会2`: *meeting* (noun, level 3)                          |
| 站1 / 站2   | zhàn   | `站1`: *station / stop* (noun, level 2)        | `站2`: *to stand* (verb, level 3)                         |
| 过去1 / 过去2 | guòqù  | `过去1`: *to pass / to go over* (verb, level 2) | `过去2`: *the past* (noun, level 3)                        |
| 花1 / 花2   | huā    | `花1`: *to spend (money/time)* (verb, level 2) | `花2`: *flower; floral* (noun level 2, adjective level 6) |

</details>

### Stage 1 (PDF Parsing → Raw Rows)

Code path:
- `src/hsk_pipeline/stages/stage1_extract.py`
- `extract_text_lines()`
- `parse_entries()`
- `parse_levels()`
- `split_pos_groups()`
- `_replace_cid_tokens()`

Rules:
- Parses entry lines with numeric index + level + remaining fields.
- Handles delayed-Hanzi PDF artifacts by buffering a pending entry (`PendingEntry`) until a Hanzi-only line arrives.
- Supports known CID replacement and missing-word overrides for extraction defects.
- Splits multi-level rows like `1（4）` into multiple rows and aligns POS groups from parenthesized segments.
- Preserves sense suffixes in the output word (`点1`, `点2`, etc.) at Stage 1.

### Stage 2 (Add `pinyin_numbered`)

Code path:
- `src/hsk_pipeline/stages/stage2_number.py`
- `add_pinyin_numbered()`
- `pinyin_numbered()`
- `_segment_pinyin_with_hanzi()`
- `_pinyin_numbered_basic()`

Rules:
- Normalizes source pinyin (tones expressed as trailing numbers) and lowercase before segmentation.
- Preserves `/` as an alternate-reading separator in output.
- Uses CC-CEDICT Hanzi/word syllable maps from `CedictRepository` to align syllable boundaries to Hanzi.
- Keeps neutral tone as `5`.
- Supports syllabic interjections (`m`, `n`, `ng`, `hm`, `hng`, `r`).

### Stage 3 (Add `pinyin_cc-cedict` + `definition_cc-cedict`)

Code path:
- `src/hsk_pipeline/stages/stage3_enrich.py`
- `enrich_with_cedict()`
- `_resolve_from_repo()`
- `_lookup_word()`
- `src/hsk_pipeline/cedict/matcher.py`
- `src/hsk_pipeline/cedict/parser.py`

Resolution order per row:
1. Exact numbered-pinyin match.
2. Tone-insensitive unique match.
3. Tone-insensitive multi-match resolved by `data/disambiguation.tsv`.
4. Patch fallback using `data/cedict_patch.u8`.
5. No match → fail by default (`--allow-unresolved` overrides this).

Sense suffix handling:
- For lookup only, non-Hanzi suffixes are stripped (`_lookup_word()`), so `点1`/`点2` are looked up as `点`.
- Output still preserves original `word` from the HSK row.

### Multiple CC-CEDICT Definitions

Code path:
- `src/hsk_pipeline/cedict/parser.py::parse_cedict_lines()`
- `src/hsk_pipeline/cedict/matcher.py::group_candidates()`

Behavior:
- Each CC-CEDICT line definition is normalized by splitting slash-glosses and joining them with `; `.
- If multiple CC-CEDICT entries map to the same `(word, pinyin)` candidate, their definitions are all kept and merged deterministically using ` | `.
- The selected Stage 3 candidate writes that merged definition into `definition_cc-cedict`.
- So it is not "first definition only"; merged definitions are used for duplicate same-pinyin candidates.

### Capitalization Handling in Matching

Code path:
- `src/hsk_pipeline/stages/stage2_number.py::pinyin_numbered()`
- `src/hsk_pipeline/cedict/parser.py::normalize_cedict_syllable()`
- `src/hsk_pipeline/cedict/matcher.py::tone_insensitive_tokens()`

Behavior:
- Pinyin matching is case-insensitive because both source pinyin and CEDICT pinyin are lowercased before comparison.
- Tone-insensitive matching removes tone numbers only; token boundaries still must match.
- Definitions are not used as match keys, so definition capitalization does not affect matching.
- Definition text is preserved from CEDICT (apart from slash-to-`; ` normalization and possible ` | ` merge).

## Contributing

Contributions are welcome, especially in these areas:
- Bug fixes on the code to improve processing.
- Integrations for HSK 3.0 (2021) and HSK 2.0.
- Corrections to `data/cedict_patch.u8` and `data/disambiguation.tsv`.

## License

This project is licensed under the MIT License. See `LICENSE` for details.

This project also uses CC-CEDICT data obtained at:
- https://cc-cedict.org/

CC-CEDICT is licensed under CC BY-SA 4.0 (Attribution-ShareAlike 4.0).
- https://creativecommons.org/licenses/by-sa/4.0/
