# HSK 3.0 (2026) Word List TSV Extractor

This module extracts the **HSK 3.0 (2026)** vocabulary list into a TSV file. The updated HSK 3.0 list was released in **November 2025** and is scheduled to be implemented in **July 2026**.

The goal of this project is to produce a list of Chinese words per **HSK level** where **both Hanzi and pinyin are present**. Many existing HSK vocabulary lists only store Hanzi, which is not sufficient for uniquely identifying a word because multiple words can share the same Hanzi with different pronunciations.

**Input Source:** 
- Syllabus for the Chinese Proficiency Test. 
- Download: [新版HSK考试大纲（词汇、汉字、语法）](https://hsk.cn-bj.ufileos.com/3.0/%E6%96%B0%E7%89%88HSK%E8%80%83%E8%AF%95%E5%A4%A7%E7%BA%B2%EF%BC%88%E8%AF%8D%E6%B1%87%E3%80%81%E6%B1%89%E5%AD%97%E3%80%81%E8%AF%AD%E6%B3%95%EF%BC%89.pdf)

**AI usage notice:** A model was used to generate the processing script and this README file.


## Output Format

| word_index | level | word | pinyin  | pinyin_numbered | part_of_speech |
|-----------:|------:|------|---------|-----------------|----------------|
|          1 |     1 | 爱    | ài      | ai4             | 动              |
|          2 |     1 | 八    | bā      | ba1             | 数              |
|          3 |     1 | 爸爸   | bàba    | ba4 ba5         | 名              |
|          4 |     1 | 吧    | ba      | ba5             | 助              |
|          5 |     1 | 白天   | báitiān | bai2 tian1      | 名              |
|          6 |     1 | 百    | bǎi     | bai3            | 数              |
|          7 |     1 | 半    | bàn     | ban4            | 数              |
|          7 |     4 | 半    | bàn     | ban4            | 副              |
|          8 |     1 | 包子   | bāozi   | bao1 zi5        | 名              |

Generated output file: [`hsk_word_list.tsv`](./hsk_word_list.tsv)

## Output Quality

A manual (human-done) check was performed by comparing all the entries on the first and last pages of the original syllabus with the output of the script, and the information matched. Further quality analysis is recommended. If you identify any problems, please open an issue.


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

Formatting conventions used in the source:
- Multiple pinyin pronunciations in `pinyin` are separated by `/` (e.g., `shéi/shuí`).
- Multiple part-of-speech labels in `part_of_speech` are separated by `、`.
- Some syllabus entries include internal pinyin spaces to show sub-word boundaries (e.g., `打电话` as `dǎ diànhuà`). In the extractor output, this internal space is removed in `pinyin` (output: `dǎdiànhuà`).

If a word appears in multiple levels, the syllabus uses parentheses in both the `level` and `part_of_speech` columns. For example:
- `level`: `1（4）`
- `part_of_speech`: `形、介、（动、量）`

In those cases, the extractor **creates multiple entries**, one per level, repeating the **same word index** (so it's easier to compare the script's result with the syllabus) and other fields with the corresponding part-of-speech group.

### Sense Suffixes in `word` (`1` / `2`)

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
- **PDF extraction issues**: some lines contain pinyin before Hanzi. The extractor buffers these and attaches the next Hanzi-only line. Page marker artifacts like `汉/国/际/考` are ignored while waiting.
- **Other PDF extraction issues**: a small override table patches the known missing Hanzi cases where the PDF layout extraction fails.

## Output TSV Analysis Tables

The tables below come from the current generated `hsk_word_list.tsv`.

### Word Count by HSK Level

| level | word_count |
|-------|-----------:|
| 1     |        300 |
| 2     |        204 |
| 3     |        507 |
| 4     |       1019 |
| 5     |       1638 |
| 6     |       1815 |
| 7-9   |       5622 |

### Part-of-Speech Tokens Present

| part_of_speech | translation               | count |
|----------------|---------------------------|------:|
| 动              | verb                      |  4543 |
| 名              | noun                      |  4495 |
| 形              | adjective                 |  1684 |
| 副              | adverb                    |   522 |
| 量              | measure word / classifier |   177 |
| 连              | conjunction               |   115 |
| 代              | pronoun                   |    82 |
| 介              | preposition               |    65 |
| 助              | particle                  |    27 |
| 数              | numeral                   |    26 |
| 后缀             | suffix                    |    19 |
| 数量             | quantifier                |    14 |
| 叹              | interjection              |    10 |
| 前缀             | prefix                    |     5 |
| 拟声             | onomatopoeia              |     3 |
