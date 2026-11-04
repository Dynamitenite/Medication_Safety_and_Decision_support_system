# AI-Powered Personalized Medication Safety and Decision Support System

## 1. Project

Course 24RM604, Group 4. Partner: Selvam Medicals. Guide: Dr. T. Senthil Kumar.

The app helps a person keep track of their medicines and check a new one before taking it. A user signs in, enters a profile (age, height, weight), allergies, conditions and the medicines they take now or took before, and sees them as lists and timelines. To add a medicine they type its name or scan a printed prescription. The app then checks the new medicine against the current ones and the recorded allergies, shows a level (Medium, High or Critical) with the reason, asks for an acknowledgement when the level is Critical, and lists other brands with the same ingredients and their prices. Every result is informational. See the [disclaimer](#13-disclaimer).

## 2. Team and ownership

The Status column describes the code in this repository, not the plan.

| Member | Area | Status | What exists |
|---|---|---|---|
| Aakaash Pavangat | AI-based medication safety risk and personalized alert generation (Focal Loss with explainability) | Partly built | Built: risk levels from interaction rules and allergies, personalised to the signed-in user's medicines and allergies. Code built but **not trained**: the Focal Loss interaction-type classifier (BioBERT, BiLSTM) and its Integrated Gradients explanation. No valid training run exists, so the app shows "not ready" for it. |
| Aakaash Pavangat | AI-based medicine information retrieval and generic alternative recommendation using an LLM (cosine-similarity semantic retrieval) | Partly built | Built: same-ingredient alternatives with prices, label search and "similar uses" by cosine similarity over US label text with a TF-IDF encoder (word overlap, not deep learning). Not built: the sentence-embedding encoder (optional, `ENCODER=sbert`), and live use of the LLM step (code and tests exist; it runs only with `LLM_API_KEY` set, and no live call has been run). |
| Loganathan T | Drug-drug interaction and drug-disease interaction | Partly built | Built: drug-drug rule matching and the interaction checker, from a small synthetic rule set. Not built: drug-disease interaction (the module shows "coming soon"). |
| Milan Johnson | AI-based clinical and economic impact assessment of the medication safety system | Not built | Only the price column of the alternatives list exists; there is no impact assessment. |
| Milan Johnson | Personalized medication risk detection with explainable clinical decision support | Partly built | Built: each finding shows its level and the reason it was given (rule text or label text). No model-based risk detection. |

## 3. Features

| What a user can do | Page | API route |
|---|---|---|
| Sign in or create an account (a new email creates one), log out | `/login` | `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` |
| Keep a profile (name, date of birth, sex, height, weight, blood group) and see BMI | `/profile` | `GET`/`PUT /api/profile`, `GET /api/profile/overview` |
| Record allergies | `/profile` | `/api/allergies` (GET, POST, PUT, DELETE) |
| Record past and current conditions, with outcome | `/history` | `/api/conditions` |
| Record past and current medicines; list, timeline and table views | `/history?tab=medicines` | `/api/medicine-records` |
| Add a medicine by typing; see label text for it | `/add` | `GET /api/medicine/suggest`, `GET /api/medicine/{id}/details` |
| Add medicines by scanning a printed prescription (text is read in the browser; no image is sent to the server) | `/add?tab=scan` | none for the picture; suggestions use `GET /api/medicine/suggest` |
| Risk analysis of the new medicines against current medicines and allergies, with the Critical acknowledgement | `/add` | `POST /api/analyze`, `POST /api/medicine-records/batch` |
| Find other brands with the same ingredients, with price and pack size | `/alternatives` | `GET /api/medicine/{id}/alternatives` |
| See medicines with similar uses | `/alternatives` | `GET /api/medicine/{id}/similar-use` |
| Search the US label text of a medicine | `/medicine/:id` | `POST /api/search/labels`, `GET /api/medicine/{id}` |
| Read a US label | `/label/:setId` | `GET /api/label/{set_id}`, `GET /api/label/{set_id}/alternatives` |
| Check several medicines against each other | `/checker` | `POST /api/checker` |
| Delete the account and all its data | `/account` | `DELETE /api/account` |
| Read what data and methods the app uses | `/about/data`, `/about/trace` | `/api/datasets/*`, `/api/catalogue/*`, `/api/appms/*`, `/api/index/summary`, `/api/ddi/metrics`, `/api/status`, `/api/trace` |

## 4. Architecture

A React app (Vite) talks to a FastAPI app that lives under `/api`. Accounts, profiles and medical history are stored in a local SQLite file. Medicine names, prices and compositions come from an Indian medicine catalogue; label text for ingredients comes from DailyMed. Risk levels come from interaction rules and allergy matching; a trained classifier would only add an interaction-type estimate and never changes a level.

```mermaid
flowchart LR
  U["Browser: React app (built)"] -->|"/api (JSON, session cookie)"| A["FastAPI app, one APIRouter (built)"]
  A --> DB[("SQLite app.db: accounts, profile, history (built)")]
  A --> C["Indian medicine catalogue (built)"]
  A --> L["DailyMed label index, TF-IDF (built)"]
  A --> R["Interaction rules, synthetic seed rules (built)"]
  A --> K["Focal Loss classifier (code built, not trained)"]
  A --> M["LLM step, hosted API (built; live calls not run)"]
  L -. optional .-> S["Sentence-embedding encoder (not built)"]
```

Status of each box: React app, FastAPI app, SQLite, catalogue, label index and rules are built and tested on this machine. The classifier has code and tests but no valid training run. The sentence-embedding encoder is not built. The LLM step is built and tested with a fake provider; no live call to the hosted model has been run.

## 5. Requirements

Versions on the machine where everything below was run:

| Item | Version |
|---|---|
| OS | Windows 11 Home Single Language, 10.0.26300 |
| Python | 3.11.0 |
| Node.js | v24.11.0 (npm 11.6.1) |
| Browser for the browser scripts | Chromium installed by Playwright (`npx playwright install chromium`) |

Python packages are pinned in [aakaash/requirements.txt](aakaash/requirements.txt). Training the classifier also needs `torch` and [aakaash/requirements-train.txt](aakaash/requirements-train.txt).

## 6. Setup and run

Commands are for PowerShell on Windows, run from the repository root unless a `cd` is shown. Clone into a folder with a short path: `python -m venv` failed with "ensurepip returned non-zero exit status 1" when the clone was about 230 characters deep (Windows path-length limit), and worked at `C:\Users\<name>\AppData\Local\Temp\rmfresh`.

Backend:

```powershell
cd aakaash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:SESSION_SECRET = "<a long random string>"
.venv\Scripts\python.exe -m uvicorn api.app:app --port 8000
```

Frontend (second terminal):

```powershell
cd aakaash\web
npm ci
npm run dev
```

Open <http://localhost:5173> (if that port is busy, Vite prints the one it picked). The dev server forwards `/api` to <http://127.0.0.1:8000>; to use another API address set `MEDSAFE_API` before `npm run dev` (for example `$env:MEDSAFE_API = "http://127.0.0.1:8001"`). The API documentation is at <http://127.0.0.1:8000/docs>.

Production build and preview (the preview also forwards `/api`):

```powershell
cd aakaash\web
npm run build
npm run preview        # http://localhost:4173
```

Tests and checks (the API must be running on port 8000 for the browser scripts, and the data and indexes from section 7 must exist):

```powershell
cd aakaash
.venv\Scripts\python.exe -m pytest                  # API and parser tests
cd web
npm test                                            # parser and chart-layout tests (node --test)
npm run typecheck
npm run build
npx playwright install chromium                     # once
npm run e2e                                         # login to logout in headless Chrome
npm run visual                                      # overflow, fonts and clipped chart text at 1280 and 390 px, light and dark
npm run a11y                                        # axe-core and a keyboard-only run
```

The browser scripts take the web address as an argument and default to `http://localhost:4173` (the preview). For the dev server: `node scripts/e2e.mjs http://localhost:5173`.

Regenerate the TypeScript API types after changing the API:

```powershell
cd aakaash\web
npm run gen:types      # writes src/features/aakaash/api-types.ts from the FastAPI OpenAPI schema
```

Test results on this machine: with the packages in `requirements.txt` only (no `torch`), `pytest` gives 248 passed and 5 skipped (the classifier tests skip), in about 93 s in a fresh clone. With `torch`, `transformers` and `captum` installed (the main working copy) it gives 279 passed (73 s on one run, 310 s on a later, busier run). Training the classifier on a GPU (`notebooks/train_ddi.ipynb`) was not tested on Colab or Kaggle after the last tokenizer fix: not tested.

## 7. Data

Nothing in `data/` is in git (`.gitignore` covers `data/`, `aakaash/artifacts/`, databases, model files, `.env` and key files). The folder `data/` sits at the repository root, next to `aakaash/` and `.git`.

| Folder | What to put there | Where it comes from |
|---|---|---|
| `data/indian_meds/` | `indian_medicine_data.csv` and `updated_indian_medicine_data.csv` | The public GitHub repository "Indian-Medicine-Dataset" (MIT licence as stated by the repository; the repository does not state where its data came from) |
| `data/dailymed_rx/` | One or more `dm_spl_release_human_rx_part*.zip` | DailyMed human prescription label downloads. Only part 6 (1.87 GB) was used here; the build loops over whatever zips are present |
| `data/ddi2013/` | The DDI Extraction 2013 corpus (`DDICorpus/Train`, `DDICorpus/Test`) | DDI Extraction 2013 shared task |
| `data/appms/` | `patients.csv`, `medications.csv`, `patient_drug_pair_scenarios.csv`, `ddi_seed_rules.csv`, `data_dictionary.csv`, `README.txt` | The Tamil Nadu and Kerala synthetic medication safety dataset supplied for the project. All patients and the interaction rules are synthetic |
| `data/tac2017/`, `data/mappings/` | Optional. Empty on this machine | TAC 2017 labels and DailyMed RxNorm mappings; not used by the app |

Build the indexes (all outputs go to `aakaash/artifacts/`, which is not in git). Run in this order from `aakaash`:

```powershell
.venv\Scripts\python.exe scripts\build_names.py        # name index: artifacts\names.json
.venv\Scripts\python.exe scripts\build_catalogue.py    # catalogue: artifacts\catalogue.json
.venv\Scripts\python.exe scripts\build_index.py        # label retrieval index (TF-IDF): artifacts\index\
```

Measured on this machine with the part 6 zip (4,293 labels) and 253,973 catalogue rows. Two runs each: the first in the main working copy with the files already in the disk cache, the second in a fresh clone with cold files.

| Step | Time (main copy / fresh clone) | Output size | Source of the number |
|---|---|---|---|
| `build_names.py` | 34.5 s / 55.8 s | 4.02 MB | printed by the script |
| `build_catalogue.py` | 13.9 s / 19.0 s | 18.71 MB | printed by the script |
| `build_index.py` | 58.0 s / 104.1 s, peak RAM 355.6 MB / 311.0 MB | 266.6 MB | printed by the script |

Build `names.json` and then `catalogue.json` again after any change to `medsafe/spl.py`. The API also needs the folders `data/appms` and `data/indian_meds`; without the catalogue it reports "not ready" on the affected pages. The database `artifacts/app.db` is created on first start. `python data_report.py` rewrites `aakaash/DATASET_REPORT.md` from the real files (59 s here).

## 8. Environment variables

At startup the API server loads `aakaash/.env` if it exists (python-dotenv). Variables already set in the real environment win over the file; a missing file is ignored. Copy [aakaash/.env.example](aakaash/.env.example) to `aakaash/.env` and fill in values. `.env` is gitignored; never commit values.

| Name | Purpose | Required |
|---|---|---|
| `SESSION_SECRET` | Key that signs the session cookie. If unset, a random key is made per run and everyone is signed out at each restart | Recommended |
| `MEDSAFE_COOKIE_SECURE` | Set to `1` to force the Secure cookie flag when TLS ends at a proxy (the flag is on automatically for https requests) | No |
| `MEDSAFE_API` | Address the web dev server and preview forward `/api` to. Default `http://127.0.0.1:8000` | No |
| `MEDSAFE_DATA_DIR` | Data folder. Default `<repo>/data` | No |
| `MEDSAFE_ARTIFACTS_DIR` | Output folder. Default `aakaash/artifacts` | No |
| `ENCODER` (or `MEDSAFE_ENCODER`) | `tfidf` (default) or `sbert`. `sbert` needs the index from `notebooks/build_sbert_index.ipynb` installed with `scripts/install_sbert.py`; if it is missing or stale the app answers with TF-IDF and says so | No |
| `MEDSAFE_DEVICE` | Device for the sbert model: `cpu` (default), `cuda` or `auto`. Used by the app, by `scripts/build_index.py` (or its `--device`) and by the scripts; tests never use a GPU | No |
| `MEDSAFE_DDI_CLASSIFIER` | Which classifier run to load: `focal` (default) or `ce` | No |
| `MEDSAFE_DDI_MODEL_DIR`, `MEDSAFE_DDI_METRICS_DIR` | Override where the classifier checkpoint and metrics are read | No |
| `MEDSAFE_DDI_IG_STEPS` | Integrated Gradients steps for explanations (default 50) | No |
| `SIMILAR_USE_MIN` | Minimum similarity for "similar uses"; unset means no minimum | No |
| `LLM_API_KEY` | Key for the hosted LLM (a Google AI Studio key). Server-side only; never sent to the browser, logged or committed. Unset: the AI-written answers are hidden and the rest of the app works | No |
| `LLM_PROVIDER` | Which provider class to use. Default `gemini` | No |
| `LLM_MODEL` | Model name. Default `gemini-3.5-flash-lite` (listed Stable on Google's models page, checked 2026-11-04) | No |
| `LLM_RPM` | Requests per minute the server allows itself. Default 5. Free-tier limits per model are shown only in Google AI Studio; check yours before raising it | No |

## 9. Project layout

```
.gitignore
README.md                 this file
data/                     datasets (not in git)
aakaash/
  api/                    FastAPI app: app.py (standalone app), router.py (one APIRouter, prefix /api), auth.py, db.py, schemas.py, services/
  medsafe/                parsers (SPL labels, DDI 2013), catalogue, risk rules, chunking, encoders, index, classifier, explanations
  scripts/                build_names / build_catalogue / build_index, evaluations, training, spl_check/
  tests/                  pytest tests (fixtures are hand-written, not real data)
  notebooks/              train_ddi.ipynb (GPU training of the classifier)
  web/                    React app: src/, scripts/ (e2e, visual-check, a11y, gen-types), DESIGN.md
  artifacts/              generated files and app.db (not in git)
  CLAUDE.md, WEBAPP_PLAN.md, PAPER_TRACE.md, DATASET_REPORT.md   project notes
```

## 10. API overview

All routes are under `/api`. Interactive documentation: <http://127.0.0.1:8000/docs>; schema: <http://127.0.0.1:8000/openapi.json>.

| Group | Routes | Needs sign-in |
|---|---|---|
| Account | `/auth/login`, `/auth/logout`, `/auth/me`, `DELETE /account` | all but login |
| Profile and history | `/profile`, `/profile/overview`, `/allergies`, `/conditions`, `/medicine-records`, `/medicine-records/batch` | yes |
| Risk analysis | `POST /analyze` | yes |
| Medicines | `/medicine/suggest`, `/medicine/{id}`, `/medicine/{id}/alternatives`, `/medicine/{id}/similar-use`, `/medicine/{id}/details` | `details` only |
| Labels | `/label/{set_id}`, `/label/{set_id}/alternatives`, `POST /search/labels`, `/index/summary` | no |
| Interaction checker | `POST /checker`, `/appms/*` (synthetic sample patients and rules) | no |
| Interaction type (model estimate) | `POST /ddi/classify`, `/ddi/metrics` | no |
| Data and methods | `/datasets/*`, `/catalogue/*`, `/status`, `/trace`, `/health` | no |

## 11. Data and methods

This section uses research wording.

- **Indian medicine catalogue.** A public GitHub dataset ("Indian-Medicine-Dataset"). The repository states an MIT licence and does not state the original source of the data, so its origin is unknown. 253,973 products, 7,905 marked discontinued (printed by `build_catalogue.py`). Price, pack size and composition are as listed there and may be out of date or incomplete.
- **DailyMed labels.** Part 6 of the human prescription label release: 4,293 labels, 0 parse failures. Of these, 4,223 have an Indications section, 4,205 Contraindications and 3,602 Drug Interactions (`DATASET_REPORT.md`, regenerated by `data_report.py`). US labels are linked to catalogue ingredients by ingredient name or active moiety: 659 of 1,725 distinct catalogue ingredients (38.2%) link to at least one label, and 160,286 of 253,973 products (63.1%) have every listed ingredient linked. The other ingredients have no US label here, so the app shows no label text for them.
- **Interaction rules.** `data/appms/ddi_seed_rules.csv` is a small synthetic rule catalogue shipped with a synthetic dataset. Its own README says it is not clinically validated and that "not flagged" means unknown, not safe. The risk levels shown for interactions come from these rules; they are not a clinical source. Allergy findings match by name only.
- **Retrieval.** Cosine similarity over TF-IDF vectors of label chunks (512 words, overlap 64). This is a word-overlap baseline, not deep learning. A sentence-embedding encoder (BAAI/bge-small-en-v1.5, pretrained, not fine-tuned) is implemented behind `ENCODER=sbert`; its index is built on a free Kaggle GPU (`notebooks/build_sbert_index.ipynb`) and installed with `scripts/install_sbert.py`, but it has not been built yet, and TF-IDF stays the default. A proxy check on 100 random catalogue products (`scripts/eval_retrieval.py`; not a relevance judgement) asked whether a label of the right ingredient and section appears in the top 5 for "<ingredient> drug interactions": 19 of 82 counted products did (source: `aakaash/PAPER_TRACE.md`). No pharmacist-judged relevance set exists, so no precision or recall is reported.
- **Focal Loss classifier.** BioBERT, a BiLSTM and a focal-loss objective on DDI Extraction 2013 (train 25,037, dev 2,754, test 5,715 sentence pairs). **Not trained yet.** The first run was invalid because of a tokenizer fault, and the app hides metrics that fail its quality gate. No accuracy, F1 or speed figure is claimed.
- **Explainability.** Integrated Gradients over input words and a deletion-based faithfulness check are implemented and were run only on a tiny random model to test the code.
- **Limitations.** Only one DailyMed part is loaded. Allergy matching does not cover drug classes. The rules are synthetic. The scan reads printed text only. Nothing here replaces a pharmacist's check.

The paper trace (which design choice comes from which paper, and which is our own) is in [aakaash/PAPER_TRACE.md](aakaash/PAPER_TRACE.md) and is shown in the app at `/about/trace`.

## 12. Contributing and merging

- Branches: Aakaash's work is on `aakaash/<topic>` (existing: `aakaash/ai-components`, `aakaash/webapp`); each teammate uses their own prefix. The remote's default branch is `aakaash/ai-components`; the local `main` tracks `origin/main`. Do not push to another person's branch.
- The backend is one `APIRouter` with prefix `/api` in `aakaash/api/router.py`. A teammate can mount it in their own app with `app.include_router(router)`; `aakaash/api/app.py` is the standalone app (CORS for the dev server, error and header handlers, startup).
- To add a module: add the router functions in `aakaash/api/router.py` (or a new router file included there), the schemas in `schemas.py`, the logic in `api/services/`, tests in `aakaash/tests/`; add its React page under `aakaash/web/src/features/<you>/`, one line in `registry.ts` (`MODULE_COMPONENTS`), and run `npm run gen:types`. The module list and ids come from `api/modules.py`.
- Reuse these instead of writing your own: sign-in and the `current_user` dependency (`api/auth.py`), the profile, allergies and conditions routes, `/medicine-records` and `/medicine-records/batch`, and `POST /analyze` for risk levels.
- Rules: no secrets in git (names only in `.env.example`); no datasets, databases, indexes, checkpoints or models in git; run `pytest`, `npm test`, `npm run typecheck` and `npm run build` before you merge.

## 13. Disclaimer

Informational only. Not a substitute for advice from your doctor or pharmacist.
