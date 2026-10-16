# CarePilot AI Architectural & Clinical Decisions

## EHR Merge & Patient ID Deduplication Strategy

### Synthea Shared-ID Collision Analysis (31 Shared-Id Pairs)
During the ingestion and merger of the demo dataset (40 patients) and the 2,000-population scale dataset (2,290 patients), exactly 31 UUIDs were found to be shared between both source cohorts. Detailed manual inspection of the demographic records revealed identical patient names and genders, but discordant birthdates differing by intervals ranging from several days to several weeks, alongside disparate clinical encounters and observation timelines. This specific pattern is consistent with Synthea's pseudo-random number generator (RNG) state divergence when generating disparate cohort population sizes using the same seed, rather than a genuine identity match or an independent random collision. Consequently, for patient safety, rigorous auditability, and data integrity, these records are treated as strictly distinct individuals: all 40 demo patients have been loaded with a distinct `demo40:` ID prefix, `source_run='demo40'`, and `is_demo_fixture=true`, while the scale cohort records remain unprefixed under `source_run='scale_2k'`.

## Clinical Data Integrity & Outlier Management

### Laboratory Outlier Flagging (`lab_results.is_outlier`)
To protect downstream clinical reasoning prompts and retrieval components from synthetic generation formula artifacts and unbounded simulation drift without modifying or corrupting the underlying deterministic raw Synthea observation values, a dedicated boolean column `is_outlier` (default `FALSE`) is maintained on `lab_results`. Outliers are identified and flagged as `TRUE` according to the following physiological bounds:
1. **Creatinine (`38483-4`)**: Flagged when `numeric_value < 0.1` or `numeric_value > 30.0 mg/dL`. While Synthea models severe Chronic Kidney Disease (Stages 1–4) longitudinally, it compounds end-stage renal decline exponentially without human survival limits or dialysis intervention, yielding mathematical values up to 101.8 mg/dL.
2. **LDL Cholesterol (`18262-6`)**: Flagged when `numeric_value < 0.0` or `numeric_value > 400.0 mg/dL`. Synthea calculates LDL via the Friedewald equation without an essential non-negative clamp (`max(0, ...)`), producing negative values (e.g. -17.4 mg/dL) during severe congestive heart failure malnutrition where Total Cholesterol is depressed and HDL + (Triglycerides / 5) exceeds Total Cholesterol.

## Knowledge Base Corpus Expansion & Coverage Decisions

### Snapshot v5.1 Incremental Addition
1. **Alendronic acid (Alendronate Sodium)**: In Synthea, oral bisphosphonate therapy is represented by the INN term `Alendronic acid 10 MG Oral Tablet`. OpenFDA queries for `alendronic acid` returned HTTP 404 (US labels index under USAN `ALENDRONATE SODIUM`). Searching `openfda.generic_name:"alendronate"` yielded the official FDA label for Alendronate Sodium (Binosto, `set_id=09765234-01bc-40f7-b9bb-c167056f3909`). This was ingested as `KB-FDA0152` into Snapshot v5.1.
2. **Etonogestrel implant (Nexplanon)**: Querying `openfda.brand_name:"nexplanon"` resolved the official FDA label for Etonogestrel subdermal implant (`set_id=487f8a62-e142-457c-97cc-2e398fde7594`). This was ingested as `KB-FDA0153` into Snapshot v5.1.
3. **Documented Gaps (Intentionally Omitted)**:
   - `tropicamide 5 MG/ML Ophthalmic Solution` (148 patients): Diagnostic pupil-dilation drops used during routine eye exams; low clinical reasoning complexity.
   - `Natazia 28 Day Pack` (138 patients): Complex quadriphasic oral contraceptive pack containing dienogest and estradiol valerate; progestin and estrogen class actions are already comprehensively represented across numerous oral contraceptive labels (e.g. Levora, Seasonique, Yaz, Trinessa, Jolivette).
   - `Unemployed (finding)` (669 patients): Non-clinical social determinant of health with no dedicated standalone clinical monograph on MedlinePlus.


## Safety & Governance: Red-Flag Lexicon Freezing

### Expansion from 9 to 11 Categories (Pillar C Pre-Flight)
Per Appendix C and Master Spec Section 6, the rule-based red-flag engine in `backend/app/pipeline/redflag.py` was expanded from 9 categories to all 11 clinical emergency categories:
1. `chest_pain` (Cardiac / Chest Pain Alert)
2. `respiratory_distress` (Severe Respiratory Distress)
3. `stroke_indicators` (Neurological / Stroke Indicator)
4. `acute_hemorrhage` (Acute / Uncontrolled Hemorrhage)
5. `syncope_seizure` (Syncope / Seizure / Consciousness Loss)
6. `anaphylaxis` (Severe Allergic Reaction / Anaphylaxis)
7. `self_harm` (Self-Harm / Psychiatric Emergency)
8. `meningitis_sepsis` (Acute Sepsis / Meningeal Sign)
9. `acute_abdomen_gi_bleed` (Acute Abdomen / Severe GI Bleed)
10. `sudden_severe_headache` (Sudden Severe Headache / Thunderclap / SAH) [Added 2026-10-15]
11. `overdose_poisoning` (Drug Overdose / Toxic Poisoning) [Added 2026-10-15]

- **Frozen SHA-256 (`redflag.py`)**: `525f2acd5159254c53716af4cc6dacd952f5e451fec8205c3699186e6b338126`
- **Validation**: Verified against 88-test matrix in `backend/tests/test_redflag_11_categories.py` covering positive, negated, historical, hypothetical, and typo/variant queries across all 11 categories (100% pass).

