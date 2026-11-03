# Dataset report

Generated 2026-11-04 00:04 by `aakaash/data_report.py` (default arguments). Every count below was produced by running the parsers on the real files; sections marked NOT RUN had no data present.

## DailyMed Rx labels (Subarea A source)

Parts loaded (no cap):

| part zip | labels parsed | parse failures | other stats |
|---|---|---|---|
| dm_spl_release_human_rx_part6.zip | 4293 | 0 | {"other_member_.jpg": 29935, "note_precautions_only_subsections": 16, "note_patient_counseling_only_subsections": 9} |

- Labels parsed: 4293
- Distinct set ids: 4293
- Distinct active ingredients (normalised strings): 1156
- Labels with no ingredient found: 0
- Labels with none of the 8 sections found: 58
- Ingredient source counts: {'ACTIB': 3030, 'ACTIM': 1041, 'ACTIB+ACTIM': 91, 'ACTIB+ACTIR': 5, 'ACTIM+ACTIR': 14, 'ACTIR': 107, 'ACTIB+ACTIM+ACTIR': 5}
- Section detection method counts: {'loinc_code': 39078, 'title_fallback': 308, 'title_over_code': 1}
- Chunking: size=512, overlap=64, unit=whitespace words

| section | labels with section | section blocks | median chars per label | chunks |
|---|---|---|---|---|
| indications | 4223 | 4226 | 957 | 4601 |
| contraindications | 4205 | 4206 | 436 | 4207 |
| warnings_precautions | 4126 | 4140 | 6526 | 12864 |
| precautions | 1369 | 1514 | 3222 | 2500 |
| boxed_warning | 1576 | 1582 | 1538 | 1725 |
| adverse_reactions | 4217 | 4218 | 5332 | 11619 |
| drug_interactions | 3602 | 3703 | 2386 | 5405 |
| specific_populations | 3855 | 5301 | 5741 | 10816 |
| dosage_administration | 4225 | 4243 | 3601 | 8610 |
| patient_counseling | 3642 | 3683 | 2360 | 5073 |
| patient_information | 2175 | 2197 | 10296 | 8662 |
| instructions_for_use | 253 | 374 | 5817 | 1267 |

Total chunks: 77349

## DailyMed mapping files

NOT PRESENT: `C:\Users\aakaa\Documents\RM\Medication_Safety_and_Decision_support_system\data\mappings` is empty. Not parsed yet.

## DDI Extraction 2013 (Subarea B source)

XML files by split (classified by folder name): {'train': 714, 'test': 191, 'excluded_ner': 112, 'unclassified': 0}

Dev split: 10% of train, stratified by label and grouped by document, seed 13. Entity markers: [['<e1>', '</e1>'], ['<e2>', '</e2>']]

| class | train | dev | test |
|---|---|---|---|
| effect | 1518 | 169 | 360 |
| mechanism | 1187 | 132 | 302 |
| advise | 743 | 83 | 221 |
| int | 171 | 17 | 96 |
| false | 21418 | 2353 | 4736 |
| **total** | 25037 | 2754 | 5715 |

Imbalance ratio = (count of `false`) / (count of class):

| split | class | false : class |
|---|---|---|
| train | effect | 14.11 |
| train | mechanism | 18.04 |
| train | advise | 28.83 |
| train | int | 125.25 |
| dev | effect | 13.92 |
| dev | mechanism | 17.83 |
| dev | advise | 28.35 |
| dev | int | 138.41 |
| test | effect | 13.16 |
| test | mechanism | 15.68 |
| test | advise | 21.43 |
| test | int | 49.33 |

By source: {"train": {"drugbank": 23392, "medline": 1645}, "dev": {"drugbank": 2613, "medline": 141}, "test": {"drugbank": 5265, "medline": 450}}

Parser statistics (skips and anomalies): {"train": {"documents": 714, "sentences": 6976, "documents_without_pairs": 90, "entities": 14765, "pairs": 27792, "instances": 27791, "discontiguous_entities": 38, "entity_text_mismatch": 38, "true_without_valid_type_treated_false": 1, "skipped_overlapping_entities": 1}, "test": {"documents": 191, "sentences": 1299, "entities": 3040, "pairs": 5716, "instances": 5715, "discontiguous_entities": 9, "entity_text_mismatch": 9, "skipped_overlapping_entities": 1}}

## TAC 2017 ADR labels (parser sanity-check set)

NOT RUN: no `.xml` files found in `C:\Users\aakaa\Documents\RM\Medication_Safety_and_Decision_support_system\data\tac2017`.
