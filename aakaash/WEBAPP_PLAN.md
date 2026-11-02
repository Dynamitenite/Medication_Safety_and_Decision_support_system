# Web app plan (Phase 0)

Branch: `aakaash/webapp`, created from `aakaash/ai-components` at `8f824dc`. No app code has been written yet.
Every fact in section 1 comes from a command run on 2026-10-16. Section 5 lists the questions that block later phases.

---

## 1. Findings

### 1.1 Repo and teammates

```
.
./aakaash            (.gitkeep, .install_log.txt, CLAUDE.md, DATASET_REPORT.md, PAPER_TRACE.md,
                      artifacts/, data_report.py, medsafe/, papers/, tests/, .venv/)
./data               (dailymed_rx/, ddi2013/, mappings/, tac2017/)  -- gitignored
```

- There are **no teammate folders** in this repo, and so no teammate frontend or backend whose stack I could see.
- `git ls-remote --heads origin` shows a single branch, `refs/heads/aakaash/ai-components`. **There is no `main` branch locally or on the remote.** Teammates' code must live in another repo or has not been pushed yet. I need to know where it lives before any merge (question Q9).

### 1.2 Tooling (venv `aakaash/.venv`)

| item | version | import check |
|---|---|---|
| Node | v24.11.0 | |
| npm | 11.6.1 | |
| Python | 3.11.0 | |
| torch | 2.14.1+cpu | imports (cold import 44.0 s); `cuda False` |
| transformers | 5.19.0 | imports (cold import 75.6 s) |
| sentence-transformers | 6.1.0 | imports (42.0 s) |
| faiss-cpu | 1.15.1 | imports |
| captum | 0.9.0 | imports |
| scikit-learn | 1.9.1 | imports |
| pandas / pyarrow / lxml | 3.0.6 / 26.0.0 / 6.1.3 | imports |
| fastapi / uvicorn | 0.143.2 / 0.54.0 | imports |
| httpx / pydantic | 0.28.1 / 2.14.1 | listed |
| pytest | 9.1.1 | in `.venv` |

Contrary to the earlier timeouts, `.install_log.txt` ends with `ALLDONE`, and all the heavy packages import. They are slow to import cold, so the API must **lazy-load** torch and transformers and must never import them at startup.
Tests use pytest (`.venv/Scripts/python.exe -m pytest` from `aakaash/`).
Hardware at the time of checking: no GPU, 15.7 GB RAM total with **2.4 GB free**, and 42 GB free on C:.

### 1.3 Data on disk

| folder | size | files | status |
|---|---|---|---|
| `data/ddi2013` | 11 MB | 1,026 (incl. `.gitkeep`, `.DS_Store`) | Present. Train: 572 DrugBank + 142 MedLine. Test (DDI task): 158 DrugBank + 33 MedLine. The DrugNER test set is excluded. |
| `data/tac2017` | 0 | only `.gitkeep` | **MISSING** |
| `data/dailymed_rx` | 0 | only `.gitkeep` | **MISSING**, with no partial or in-progress files in the folder |
| `data/mappings` | 0 | only `.gitkeep` | **MISSING** |

- The DDI corpus folder holds **only XML**: no README, annotation guidelines or class definitions.
- Pair counts in `DATASET_REPORT.md` match your numbers: train **27,792 pairs** and test **5,716 pairs**. The parser writes one fewer instance per split (train+dev 25,037 + 2,754 = 27,791; test 5,715) because it skips one pair with overlapping entities in each split (`skipped_overlapping_entities: 1`). The dashboard will show pairs and instances side by side, labelled.
- `type=` attribute counts in Train/DrugBank, from a grep: effect 1,535, mechanism 1,257, advise 818, int 178.

**Consequence:** Phase 3 (retrieval and alternatives) and Phase 5 (alert) both need DailyMed labels, so they **cannot run** until at least one DailyMed zip is in `data/dailymed_rx`. Phases 1, 2 and 4 depend only on DDI 2013 and can go ahead.

### 1.4 What `medsafe/spl.py` extracts (code reading only; never run on a real SPL file)

| field | how | captured? |
|---|---|---|
| set id | `<setId root=...>` | yes |
| title | document `<title>` text | yes |
| version, effective time | `<versionNumber value>`, `<effectiveTime value>` | yes |
| product name(s) | every `manufacturedProduct/name` in the document | yes (list, deduplicated) |
| **active ingredient(s)** | `<ingredient classCode="ACTIB">` names first, else `ACTIM`, else any `activeMoiety/name`. Normalised: lowercase, parentheticals dropped, spaces collapsed. **Salts are not stripped.** `ingredient_source` records which rule fired. | **yes**, but the structure is a guess from memory |
| sections | LOINC codes: 34067-9 indications, 34070-3 contraindications, 34071-1 + 43685-7 warnings_precautions, 34066-1 boxed_warning, 34084-4 adverse_reactions, 34073-7 drug_interactions, 43684-0 / 42228-7 / 34081-0 / 34082-8 specific_populations. A title regex is the fallback. A matched section is taken whole, subsections included. | yes, codes UNVERIFIED |
| labeler / manufacturer | — | **no** |
| generic name (`asEntityWithGeneric`) | — | **no** |
| RxNorm ids | — | **no** (mapping files missing) |

Caveats that matter for generic alternatives:
1. All ingredients from all products in one SPL go into a single list per label. A kit or multi-product label gets the union.
2. Ingredient classes other than ACTIB/ACTIM are ignored. Whether real files use other active classes is UNVERIFIED.
3. Without salt stripping or RxNorm, "metformin hydrochloride" and "metformin" count as different ingredients.
4. Without the labeler, two products from different companies cannot be told apart by name alone, only by set id and title.

### 1.5 Baseline paper (read in full: `papers/baseline_cdss.pdf`, 6 pages, pp. 1192-1197)

The five requirements check out against the text. Section locations as found:

| # | requirement | where in the PDF |
|---|---|---|
| R1 | Analyse a medication profile; alert on interactions, contraindications, allergies, side effects | §IV-C "Medication and Treatment Management" (p. 1194); §III-E "Reduction in Medical Errors" (p. 1194) |
| R2 | Explainability: decision rationales, visual explanations, feature-importance maps | §V-C (p. 1195); §VI-E "feature importance maps" (p. 1196); §VII-A "interactive visualizations ... clear decision rationales" (p. 1196) |
| R3 | Privacy and security | §V-A (p. 1195) |
| R4 | FHIR interoperability (future work) | §V-D (legacy systems, standardized formats; does **not** name FHIR); §VII-B names "HL7 FHIR" (p. 1196) |
| R5 | User-friendly interface | **Abstract only** ("user-friendly interfaces"). §VII does **not** use that phrase. The nearest is §VII-A "interactive visualizations". I will cite "Abstract" for R5 and "§VII-A (interactive visualizations)" separately, unless you say otherwise. |

The paper has no architecture. Fig. 1 shows the benefits of a CDSS and Fig. 2 its application areas. I will cite none of its references.

---

## 2. Architecture (team six-stage design, my stages only)

| stage | my component | backend interface | first implementation |
|---|---|---|---|
| 2 Information extraction & retrieval | label parsing, chunking, index, retrieval | `Encoder.encode(texts) -> ndarray` (L2-normalised); `Index.search(vec, k)` | `TfidfEncoder` (**baseline encoder**, cosine similarity, NOT deep learning) |
| 4 AI risk & safety engine | DDI type classification | `DDIClassifier.predict_proba(sentence, e1_span, e2_span) -> {effect, mechanism, advise, int, false}` and `.explain(...)` | TF-IDF + logistic regression (**classical baseline**, NOT Focal Loss, NOT deep learning) |
| 5 Recommendation engine | grounded medicine info, same-ingredient alternatives | uses `Index` and label metadata | |
| 6 Explanation generator | evidence cards, top-token explanation, deterministic alert template | | |

- The checker receives its medicine list in the request body and stores nothing. Since the accounts update (section 7) a signed-in person's profile and medical history are stored in a local SQLite database.
- The active encoder and classifier are chosen in `aakaash/api/config.py` (overridable by environment variable) and reported by `/api/status`. A future Focal Loss or BioBERT model only needs to implement `DDIClassifier`.

### File layout (proposed)

```
aakaash/
  api/
    __init__.py
    router.py         APIRouter(prefix="/api"): the only thing the team needs to include_router
    app.py            standalone FastAPI app + CORS for the Vite dev server (localhost:5173)
    config.py         paths (data/, artifacts/), active encoder/classifier names
    schemas.py        pydantic response/request models
    services/         status.py, datasets.py, trace.py, retrieval.py, ddi.py, alert.py
  medsafe/
    encoders.py       Encoder interface + TfidfEncoder
    index.py          build/load/search; numpy dot product over normalised vectors (or faiss, both installed)
    ddi_models.py     DDIClassifier interface + LinearBaselineClassifier
  scripts/
    build_index.py         CLI: chunks -> encoder -> artifacts/index/, logs counts and time
    train_ddi_baseline.py  CLI: train / tune on dev / report test -> artifacts/ddi_baseline/{model,metrics.json}
  tests/test_api.py   pytest, fixtures only (clearly labelled), FastAPI TestClient
  web/                Vite + React 18 + TypeScript + React Router + Recharts
    src/app/          shell, sidebar, banner, router (built from the registry)
    src/features/aakaash/
      registry.ts     every module: id, route, label, stage, status (ready | not_ready | coming_soon), owner
      api.ts          typed fetch client
      pages/          Dashboard, MedicineInfo, InteractionRisk, PersonalizedAlert, Trace, About, ComingSoon
      components/     StatusCard, StateGate (loading/error/not_ready), EvidenceCard, TokenHighlight, ...
  artifacts/          gitignored: ddi2013 jsonl, index, model, metrics
```

Planned installs (small): `pytest` (Phase 1 asks for pytest). The npm packages for `web/` are react, react-dom, react-router-dom, recharts, vite and typescript. Nothing else.

---

## 3. Endpoints

| method | path | returns | data dependency |
|---|---|---|---|
| GET | `/api/health` | `{status: "ok"}` | none |
| GET | `/api/status` | per component (ddi_data, tac_data, dailymed_data, encoder, index, ddi_model): `ready` / `not_ready` + `reason` + `fix`; plus the `coming_soon` modules; plus active encoder/classifier names | filesystem checks only |
| GET | `/api/datasets/ddi2013/stats` | pairs and instances per split, counts per class per split, false:class ratios, by-source counts, parser skip stats | runs `medsafe.ddi2013` on `data/ddi2013` (cached in memory after the first call) |
| GET | `/api/datasets/ddi2013/examples?split=&label=&limit=` | real instances with `<e1>`/`<e2>` marked, doc id, source | same |
| GET | `/api/datasets/dailymed/stats` | labels parsed, per section, chunks, distinct ingredients, parse failures, parts loaded, or `not_ready` | `data/dailymed_rx/*.zip` |
| GET | `/api/datasets/tac2017/stats` | counts, or `not_ready` | `data/tac2017` |
| GET | `/api/trace` | rows of `PAPER_TRACE.md` (component, file, source, note, status) + a source category: FROM PAPERS / FROM BASELINE REVIEW / NOT IN PAPERS | file |
| POST | `/api/retrieve` `{query, k, section?}` | top k: chunk id, set id, title, drug/product name, ingredients, section, cosine score, text, encoder name + `is_deep_learning: false` | index (Phase 3) |
| POST | `/api/alternatives` `{medicine}` | resolved ingredient set, then labels sharing it, each with set id, title, product names and the source of the match | index metadata (Phase 3) |
| GET | `/api/ddi/model-card` | classifier name, kind (baseline / not focal loss), training config, per-class P/R/F1 + support on test, micro P/R/F1 over the 4 positive classes, read from `metrics.json` | trained model (Phase 4) |
| POST | `/api/ddi/classify` `{sentence, e1:{start,end}, e2:{start,end}}` | probabilities over 5 classes, predicted class, top contributing tokens with weights | trained model (Phase 4) |
| POST | `/api/alert` `{profile, medicine}` | alert sentences, each linked to a chunk id or a model output; evidence list | index + model + approved pair-to-sentence step (Phase 5) |

Without its data, every endpoint returns a typed `not_ready` payload with HTTP 200 and `{status: "not_ready", reason, fix}`. It never returns placeholder numbers. `/api/ddi/model-card` is an extra endpoint I added for the Phase 4 model card.

Entities are passed as character **offsets** (`{start, end}`), not names. A drug name can appear twice in a sentence, and offsets are what the DDI parser uses. In the UI you select text to mark e1 and e2.

---

## 4. Screens and build order

Permanent banner: "Research prototype. Decision support only. Not medical advice."
Sidebar driven by `registry.ts`. Every panel has loading, error and `not_ready` states, and a `not_ready` panel shows the reason and the fix instead of an empty chart.

| page | content | ready when |
|---|---|---|
| Dashboard | component status cards; DDI class distribution (log y axis) per split; imbalance table; DailyMed/TAC cards (`not_ready` today) | Phase 2 |
| Medicine Info | search box, section filter, evidence cards (label, section, score), the encoder in use + "baseline encoder: cosine similarity over TF-IDF, not deep learning"; alternatives with "alternatives are informational; a professional confirms any substitution." | Phase 3 (needs DailyMed) |
| Interaction Risk | sentence box, mark e1/e2 by selection, probabilities bar, predicted class, highlighted tokens, model card with per-class table, "classical baseline, not Focal Loss, not deep learning" | Phase 4 |
| Personalized Alert | profile form (approved fields only), alert, evidence panel | Phase 5 (needs DailyMed + Q1) |
| Trace | `PAPER_TRACE.md` table, grouped FROM PAPERS / FROM BASELINE REVIEW (ICMLAS 2025) / NOT IN PAPERS, with status column | Phase 2 |
| About | scope, the 5 baseline requirements with section citations, limitation: what is stored (accounts, profile and history in a local SQLite file), future work (FHIR, deployment, deep models) | Phase 2 |
| Coming soon (×N) | name, stage, "Coming soon", "Owner: to be confirmed", nothing else | Phase 2 |

Build order and stop points:
1. **Phase 1:** API skeleton, `/health`, `/status`, DDI stats/examples, DailyMed/TAC stats (`not_ready`), `/trace`, pytest with fixtures. Commit.
2. **Phase 2:** React shell, registry, Dashboard, Trace, About, Coming-soon pages. Commit.
3. **Phase 3:** Encoder interface, TF-IDF encoder, index CLI, `/retrieve`, `/alternatives`, Medicine Info page. **Blocked until DailyMed data and Q2 / Q6 are answered.** STOP: show index size and real queries.
4. **Phase 4:** DDIClassifier interface, linear baseline, training script, metrics, `/ddi/classify`, `/ddi/model-card`, Interaction Risk page. STOP: show real metrics. (Can run before Phase 3, since it needs only DDI 2013.)
5. **Phase 5:** `/alert` + page. **Blocked on Phase 3 and Q1 / Q5.**
6. **Phase 6:** verify, README, PAPER_TRACE update.

Because DailyMed is missing, I propose the order **1 → 2 → 4 → (3 → 5 once data arrives) → 6**. Say if you want a different order.

Proposed defaults for the DDI baseline (all NOT IN PAPERS; no answer needed unless you object):
- Input: the marked sentence, with the markers kept as tokens. Word 1–2-gram TF-IDF. `LogisticRegression` (gives probabilities).
- Tuned on dev over `C` and `class_weight ∈ {None, balanced}`. The selection metric is micro-F1 over the four positive classes (the metric definition used by P6, Eq. 1–3 per CLAUDE.md).
- The test split is used once, for the final report.
- Explanation: per-token contribution = tf-idf value × coefficient of the predicted class; top tokens are shown highlighted.

---

## 5. Questions (please answer; I have not answered them myself)

**Q1. Pair-to-sentence step (blocks Phase 5).** DDI 2013 is sentence-level. Your proposed pipeline: for "medicine + profile medicine", take the medicine's label `drug_interactions` chunks, keep sentences that mention the profile medicine by name, and classify each one. This is NOT IN PAPERS and has a domain-shift risk (training sentences are DrugBank/MedLine text, not current label text). Please confirm, and also answer:
  - a. Search both directions (the medicine's label for the profile medicine, **and** the profile medicine's label for the medicine), or only the first?
  - b. In the sentence, e1 = the medicine and e2 = the profile medicine. How should the medicine itself be located in its own label sentence, which often says "this drug" or uses the brand name? My proposal: match its product name or ingredient names; if no mention is found, skip classification and show the sentence as retrieved evidence only.
  - c. Name matching: profile medicine string only (case-insensitive, as you wrote), or also its resolved active-ingredient names?
  - d. Sentence splitting: a simple regex splitter (NOT IN PAPERS, no new package). OK?

**Q2. DailyMed subset (blocks Phase 3).** `data/dailymed_rx` is empty. Which file(s) should I index first (for example `dm_spl_release_human_rx_part1.zip` only), and with what cap on labels (`--max-labels-per-part`)? The chunker streams to disk. TF-IDF holds a sparse matrix in RAM, and only 2.4 GB was free when I checked, so I suggest starting with a capped subset. Also: should the parser be checked against real files first, with the LOINC codes and ingredient structure verified, before indexing?

**Q3. Encoder.** P1's `llmrails/ember-v1` (MIT licence, commit `5e5ce59`) is **1,340.6 MB** (`model.safetensors`; `pytorch_model.bin` is another 1,340.7 MB, but sentence-transformers fetches only one). I got this from Hugging Face's metadata API and downloaded nothing. That is over your 500 MB limit. Options: (a) approve ember-v1, (b) name a smaller model, (c) stay TF-IDF-only for now with the deep-learning encoder as a "Coming soon" slot. CPU encoding speed for any model is unmeasured.

**Q4. Coming-soon modules and stages.** Your prompt names only Stages 2, 4, 5 and 6. **What are Stages 1 and 3 called?** Proposed list, please confirm or correct:

| module | proposed stage |
|---|---|
| Allergy Check | Stage 4 (risk & safety engine) |
| Contraindication Check | Stage 4 |
| Duplicate Therapy Check | Stage 4 |
| Disease Precautions | Stage 4 (or 5?) |
| Full Patient Profile | **unknown, probably Stage 1 or 3; please tell me** |
| Deep-learning encoder | Stage 2 |
| Focal Loss interaction model | Stage 4 |

**Q5. Profile form fields (Phase 5).** P = {history, chronic diseases, allergies, current medicines}. Phase 5 uses only current medicines. Should the form show (a) only current medicines, or (b) all four fields, with the three unused ones marked "not used by this prototype yet"?

**Q6. Alternatives rule (Phase 3).** "Same active ingredient" as: an exact match of the full normalised ingredient set (so combination products match only identical combinations), with salts kept as written? Without RxNorm mappings, "X hydrochloride" ≠ "X". Do you want me to (a) keep exact matching, (b) wait for `data/mappings`, or (c) something else? Should I also extract the labeler/manufacturer from the SPL, so the UI can show which company makes each alternative?

**Q7. DDI class definitions.** `data/ddi2013` has no documentation, only XML. Please put the corpus annotation guidelines (or a README) in `data/ddi2013`, or give me approved definition text. Until then the UI shows class names only, with "definition not available".

**Q8. Severity tiers.** CLAUDE.md mentions P10's Critical/High/Advisory labels with my own assignment rules. Your web-app prompt allows only one fixed advice sentence in the alert. Should tiers be **left out** of the alert (my reading), or added?

**Q9. Teammates' code.** No teammate folders or `main` branch exist in this repo. Where does the team app live (repo/branch), and is it React + FastAPI? That decides how `router.py` and `src/features/aakaash/` get merged later. This does not block building.

---

## 6. Update 2026-11-02: Indian medicine catalogue as the primary medicine list

- The medicine list is now the Indian catalogue (public GitHub "Indian-Medicine-Dataset", `data/indian_meds/`, gitignored). `scripts/build_catalogue.py` writes `artifacts/catalogue.json`; it needs `artifacts/names.json` (`scripts/build_names.py`) for the DailyMed links.
- DailyMed is now the ingredient-level evidence source: each catalogue ingredient links to US labels by exact ingredient name, else active moiety, after the exact equivalences in `medsafe/synonyms.csv`.
- Endpoints: `/api/medicine/suggest` (matches and similar), `/api/medicine/{catalogue_id}`, `/api/medicine/{catalogue_id}/alternatives`, `/api/catalogue/summary`, `/api/label/{set_id}` and `/api/label/{set_id}/alternatives` (the former `/api/medicine/{set_id}` label endpoints), `POST /api/checker {catalogue_ids, names}`.
- Web routes: `/medicine/:id` is a brand page; `/label/:setId` is a US label page; old `/medicine/<uuid>` links redirect to `/label/<uuid>`.
- Not built: a patient store. There is no `patient_medicine` table in this repo; the patient workflow will be built later on the catalogue, storing catalogue ids.
- Real numbers (part6 of DailyMed only) are in `PAPER_TRACE.md` and on `/about/data`.

---

## 7. Update 2026-11-02: accounts, profile and medical history (task 3A)

**This adds a database, which affects how teammates merge.**

- New dependencies in the venv: `sqlalchemy` and `argon2-cffi` (there is no requirements file; run `.venv/Scripts/python.exe -m pip install sqlalchemy argon2-cffi`).
- New SQLite file `aakaash/artifacts/app.db`, created on startup (tables via `create_all`; there is no migration tool). It is gitignored with `.env` and `*.db-journal`. Never commit it. Copy `aakaash/.env.example` to `.env` and set `SESSION_SECRET` to keep sessions across restarts; without it a random key is made at startup and sessions reset.
- `api/app.py` now runs `db.session_maker(...)` in its lifespan and CORS allows credentials plus PUT and DELETE. If you mount `router` in your own app, call `db.session_maker(settings)` once at startup (it is also created lazily on first use) and keep the cookie-friendly CORS settings.
- `api/schemas.py`, `api/router.py` and `medsafe/appms.py` (a `start_date` field on `Medication`) were edited, so expect conflicts there. New files: `api/auth.py`, `api/db.py`, `api/services/accounts.py`, `api/services/prefill.py`, `medsafe/health.py`, `tests/test_accounts.py`, `tests/test_health.py`.
- Web: the signed-out app is only `/login`; search moved from `/` to `/search` (old `/?q=` links redirect). The side menu has the four task options; the old pages stay reachable by URL.

Endpoints other work can reuse (all under `/api`, all need the session cookie except `auth/login`):

| endpoint | use |
|---|---|
| `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `DELETE /account` | sign in or create, sign out, who am I, delete everything |
| `GET`, `PUT /profile` | name, date of birth (age computed), sex, height, weight (BMI computed), blood group, notes |
| `GET`, `POST /allergies`, `PUT`, `DELETE /allergies/{id}` | allergen, reaction, severity |
| `GET`, `POST /conditions`, `PUT`, `DELETE /conditions/{id}` | conditions with status (current or past) and outcome |
| `GET`, `POST /medicine-records`, `PUT`, `DELETE /medicine-records/{id}` | medicine history; `status` and `duration_days` computed; `catalogue_id` fills the name and ingredients from the catalogue; `source` is `typed` or `scanned` |

Use `api.auth.current_user` as the dependency for any new personal endpoint and always filter by `user.id`.

---

## 8. Update 2026-11-02: add new medicine, scan, risk analysis, alternatives (task 3B)

- New pages: `/add` (menu "Add new medicine"; tabs Type and Scan prescription, the "To add" list with a details card per medicine, the risk analysis and "Add to my medicines") and `/alternatives` rewritten (search, selected medicine with ingredients, strengths and price, then the existing alternative groups). `/search` stays reachable by URL. Each medicine in My medical history that came from the list has "See alternatives".
- New endpoints (all need the session cookie; none accepts a file or image):

| endpoint | use |
|---|---|
| `GET /api/medicine/{id}/details` | verbatim US label sections per ingredient, label chosen by the dosage-form rule; dosage and patient sections left out on a form, route or product mismatch |
| `POST /api/analyze` `{medicines: [{catalogue_id, course fields}]}` | levels Medium/High/Critical against the user's current medicines and allergies, read on the server; stores nothing |
| `POST /api/medicine-records/batch` `{items, acknowledged_warning}` | saves the list; re-runs the analysis and returns 409 for Critical without the acknowledgement |

- New files: `api/services/intake.py`, `medsafe/risk.py`, `tests/test_intake.py`, `web/src/features/aakaash/ocr/` (reader interface, tesseract reader, line parser and its `node --test` tests), `components/{AlternativesView,MedicineDetailsCard,RiskAnalysis,ScanPrescription}.tsx`, `pages/AddMedicine.tsx`, `toAdd.ts`, `scripts/copy-ocr.mjs`, `scripts/add-flow.mjs`. Edited: `api/router.py`, `api/schemas.py`, `api/modules.py` (Full Patient Profile no longer listed as pending), `medsafe/spl.py`, `scripts/build_names.py`, `pages/MedicinePage.tsx` (alternatives moved to a component), `pages/History.tsx`, `pages/DataMethods.tsx`, `registry.ts`, `App.tsx`, `styles.css`.
- New npm dependencies: `tesseract.js` 7.0.0 and `@tesseract.js-data/eng` 1.0.0 (exact versions). `npm run dev` and `npm run build` first run `scripts/copy-ocr.mjs`, which copies the worker, the LSTM core builds and the English model into `web/public/ocr/`. That folder is gitignored (the language data is a model file), so after a fresh clone run `npm install` and the copy happens on the next dev or build. `npm test` runs the parser tests.
- `scripts/build_names.py` now writes `instruction_sections` per label and keeps the instruction sections out of the `sections` count; rebuild `names.json` and then `catalogue.json` after pulling.
- `medicine_record.notes` holds the food timing as "Food: after food" when one was entered; there is no new column.

## 9. Update 2026-11-02: data-driven visual pass

- Added a read-only profile overview and dosage-form counts; the overview reuses the existing interaction rules and current-medicine scope.
- Added form-family, severity, allergy, and outcome icons; WHO adult BMI scale; course and history timelines; add-course bars; the risk finding graph; alternative price chart; and catalogue/rule tables paired with their charts.
- Charts use existing Recharts and are split into lazy page/chart chunks. Icon art and line illustrations are hand-drawn SVG. Search and medicine pages show only fields already present in their existing responses.
- Added fixture-only tests for BMI visibility/categories, timeline layout, price selection and interaction graph caps. No new endpoint changes a prior response; no patient, catalogue, index, model or database files were added.
