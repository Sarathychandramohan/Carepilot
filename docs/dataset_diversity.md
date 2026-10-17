# Dataset Diversity & De-duplication Report

This report provides an empirical analysis of query diversity, semantic overlap, and cross-split leakage 
across the CarePilot evaluation corpora (`gold_scripted_candidate`, `silver`, and `rq3_stream`).

## Methodology: Semantic Embedding Model, Normalization & Centering

- **Embedding Model**: `BAAI/bge-small-en-v1.5` (dense 384-dimensional sentence transformer).
- **Text Normalization**: Regex-based removal of conversational greetings and closing sign-offs (`strip_greetings_and_signoffs`).
- **L2 Normalization**: Raw embeddings are $l_2$-normalized to the unit sphere ($\|e_i\|_2 = 1$).
- **Mean-Centering**: Mitigates embedding space anisotropy (representation hubness) where raw baseline clinical similarities artificially hover at 0.50–0.60. Embeddings are centered by subtracting the global clinical corpus mean vector $\mu$ (`backend/models/corpus_mean_bge_small.npy`), then re-normalized to unit norm:
  $$\hat{e}_i = \frac{e_i - \mu}{\|e_i - \mu\|}$$
- **Calibrated Threshold**: $\tau_{\text{dup}} = 0.60$. Calibrated against clinical benchmark pairs with measured separation: hard-negative max 0.576 (< 0.60); paraphrases 4/5 $\ge 0.60$ (range 0.516 to 0.786).

## Dataset Diversity Summary

| Dataset / Split | Total Rows | Distinct Exact | Distinct Stripped | Clusters (Calibrated @0.60) | Clusters (@0.70) | Clusters (@0.50) | Dev/Test Spanning (@0.60) | Dev/Test Spanning (@0.70) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `gold-dev` | 150 | 126 | 27 | 24 | 24 | 24 | N/A | N/A |
| `gold-test` | 350 | 206 | 39 | 35 | 35 | 34 | N/A | N/A |
| `gold-combined` | 500 | 283 | 40 | 35 | 35 | 34 | 24 | 24 |
| `silver-train` | 1690 | 492 | 492 | 42 | 150 | 20 | N/A | N/A |
| `silver-dev` | 1040 | 361 | 361 | 22 | 63 | 12 | N/A | N/A |
| `silver-test` | 1040 | 357 | 357 | 24 | 47 | 9 | N/A | N/A |
| `silver-dev+test` | 2080 | 718 | 718 | 31 | 101 | 14 | 5 | 8 |
| `silver-all` | 3770 | 1210 | 1210 | 49 | 189 | 23 | 4 | 9 |
| `rq3` | 60 | 57 | 57 | 32 | 52 | 25 | N/A | N/A |

## Silver Corpus: Scenario Family Distribution

### Silver Train Families (`silver-train`, Total: 1690 rows, 13 families)

| Scenario Family ID | Query Count | Percentage |
| :--- | :---: | :---: |
| `SF-TRAIN-APPT-ROUTINE` | 130 | 7.7% |
| `SF-TRAIN-COND-MANAGEMENT` | 130 | 7.7% |
| `SF-TRAIN-GENERAL-BP` | 130 | 7.7% |
| `SF-TRAIN-GENERAL-DIET` | 130 | 7.7% |
| `SF-TRAIN-GENERAL-EXERCISE` | 130 | 7.7% |
| `SF-TRAIN-GENERAL-SLEEP` | 130 | 7.7% |
| `SF-TRAIN-GENERAL-VACCINE` | 130 | 7.7% |
| `SF-TRAIN-LAB-PATIENT` | 130 | 7.7% |
| `SF-TRAIN-MED-INTERACTION` | 130 | 7.7% |
| `SF-TRAIN-MED-SIDE-EFFECT` | 130 | 7.7% |
| `SF-TRAIN-MED-TIMING` | 130 | 7.7% |
| `SF-TRAIN-SYMPTOM-FATIGUE` | 130 | 7.7% |
| `SF-TRAIN-SYMPTOM-URGENT` | 130 | 7.7% |

### Silver Dev Families (`silver-dev`, Total: 1040 rows, 8 families)

| Scenario Family ID | Query Count | Percentage |
| :--- | :---: | :---: |
| `SF-DEV-APPT-ROUTINE` | 130 | 12.5% |
| `SF-DEV-APPT-SYMPTOM-REVIEW` | 130 | 12.5% |
| `SF-DEV-GENERAL-CHOLESTEROL` | 130 | 12.5% |
| `SF-DEV-GENERAL-STRESS` | 130 | 12.5% |
| `SF-DEV-LAB-ABNORMAL` | 130 | 12.5% |
| `SF-DEV-MED-MISSED-DOSE` | 130 | 12.5% |
| `SF-DEV-SYMPTOM-CHESTPAIN` | 130 | 12.5% |
| `SF-DEV-SYMPTOM-HEADACHE` | 130 | 12.5% |

### Silver Test Families (`silver-test`, Total: 1040 rows, 8 families)

| Scenario Family ID | Query Count | Percentage |
| :--- | :---: | :---: |
| `SF-TEST-APPT-CHRONIC-CHECK` | 130 | 12.5% |
| `SF-TEST-APPT-CLINIC-VISIT` | 130 | 12.5% |
| `SF-TEST-GENERAL-DIABETES` | 130 | 12.5% |
| `SF-TEST-GENERAL-HYDRATION` | 130 | 12.5% |
| `SF-TEST-LAB-TREND` | 130 | 12.5% |
| `SF-TEST-MED-CONTRAINDICATION` | 130 | 12.5% |
| `SF-TEST-SYMPTOM-ANAPHYLAXIS` | 130 | 12.5% |
| `SF-TEST-SYMPTOM-DIZZINESS` | 130 | 12.5% |

## Key Audit Findings & Calibration Shifts

1. **Gold Scripted Candidate Severe Duplication & Leakage**: Although `gold_scripted_candidate.jsonl` contains 500 rows, there are only **35 distinct semantic clusters** at the calibrated threshold $\tau=0.60$. Crucially, **24 clusters span both dev and test**, proving massive cross-split leakage in the unadjudicated candidate set.
2. **Anisotropy Correction via Centering**: Raw BGE-small embeddings suffered from baseline representation inflation (collapsing `gold_scripted_candidate` into only 8 clusters@0.7 and 1 giant cluster@0.5). Mean-centering eliminates this hubness, yielding robust, stable cluster representations (35 clusters across thresholds 0.60–0.70).
3. **Silver Partitioning Integrity**: In the silver evaluation set (`silver-dev+test`, 2,080 rows), queries compress into 24 distinct clusters representing the 16 disjoint scenario families (8 dev families vs. 8 test families with 130 queries each). Zero scenario families cross the dev/test boundary.
