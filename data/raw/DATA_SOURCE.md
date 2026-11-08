# Data source and licence

**Dataset:** Nawaz, S. (2026). *Academic Stress, Sleep Quality, and Lifestyle Factors Among University Students: A Cross-Sectional Dataset.* Mendeley Data, V1.  
**DOI:** [10.17632/srd3wmjd4r.1](https://doi.org/10.17632/srd3wmjd4r.1)  
**Licence:** CC BY 4.0 (attribution required)  
**Institution:** Daffodil International University  
**Content:** 300 complete survey records, 31 variables (demographics, academic background, stress/anxiety/depression ratings, sleep behaviour, lifestyle factors).

## Files
| File | Description |
|---|---|
| `Data_cleaned.csv` | Original CSV as received (whitespace trimmed and Yes/No labels standardised by the depositor); **not modified by us** |
| `test_run.jsonl` | Lossless JSON-Lines conversion of the CSV produced by `src/convert_raw.py` (file name kept from the Task 3 template) |

## Notes
- The data contain no names or direct identifiers (`Q Number` is a sequential respondent id).
- This repository performs a **secondary analysis**; we did not collect the data. Variables such as PSQI, screen time in hours and sleep-onset latency in minutes are **not** present, so the research questions were adapted accordingly (see README).
- Please cite the dataset (see above) whenever results from this repository are reused.
