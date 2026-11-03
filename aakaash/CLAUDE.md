# Claude Code prompt: Group 4 medication safety project (Aakaash's subareas)

## Current state (2026-11-04)

The text below is the original task prompt. Its rules (paper traceability, no invented numbers, no data in git) still apply. What exists now:

- The phases are done as far as the data allows. Phase 1 (parsers, chunking, dataset report) and Phase 4 (API) are built; the API is `api/router.py`, one `APIRouter` with prefix `/api`, with the routes listed in the root `README.md` (not the three routes named in Phase 4). The web app (`web/`) is a React app on that API.
- Phase 2 is built with a TF-IDF encoder (a word-overlap baseline, not deep learning). The sentence-embedding encoder (`ENCODER=sbert`) was started and not finished. The LLM step is built (`medsafe/llm.py`, `medsafe/answer.py`, `/api/answer/*`; hosted Gemini free tier, key in `LLM_API_KEY`); it is UNTESTED against the live API.
- Phase 3: the Focal Loss classifier, the Integrated Gradients explanation and the faithfulness check exist as code and tests. **No valid training run exists**, so no metric may be quoted for them. The personalised alert is rule-based (interaction rules, allergies), not model-based.
- Where to look: `README.md` (setup, data, environment), `WEBAPP_PLAN.md` section 12 (final state), `PAPER_TRACE.md` (source of every component), `DATASET_REPORT.md` (counts from the real files, regenerated 2026-11-04 by `data_report.py`), `web/DESIGN.md` (the Cluster theme).
- Checks: `pytest` in `aakaash`; `npm test`, `npm run typecheck`, `npm run build`, `npm run e2e`, `npm run visual`, `npm run a11y` in `aakaash/web`.

## PDF file mapping (read this first)

The PDFs in `aakaash/papers/` are named 1.pdf to 10.pdf in a different order than the P1-P10 labels below. Use the P-numbers in PAPER_TRACE.md, never the file numbers.

| File | Paper | P-label |
|---|---|---|
| 10.pdf | Gisladottir et al., Drug Safety | P1 |
| 9.pdf | Heiler et al., MediChat | P2 |
| 7.pdf | Zhou et al., DrugGPT | P3 |
| 8.pdf | Bang et al., Korean DUR contraindication RAG | P4 |
| 6.pdf | Li et al., EcoRxAgent | P5 |
| 3.pdf | Jia et al., BIDGNN | P6 |
| 4.pdf | Sun et al., IJMI 220 | P7 |
| 5.pdf | Draelos et al., npj Digit Med | P8 |
| 2.pdf | Krifors et al., JAMIA Open | P9 |
| 1.pdf | Shakarbaev, IJMI 215 | P10 |

Note on P4: the PDF names no journal or conference, and its reference list cites items up to 2025. Mark its venue and year as "not stated in the PDF" in PAPER_TRACE.md.

## Task

I am Aakaash (M.Tech, Group 4, course 24RM604). Implement the AI components of our project "AI-Powered Personalized Medication Safety & Decision Support System" for a project review tomorrow. The final product will be a React web app on a FastAPI backend, but today's scope is the AI models and the data pipeline only. Work only inside `aakaash/` in this repo. Teammates own the other folders.

My two subareas:

- **A. AI-Based Medicine Information Retrieval and Generic Alternative Recommendation using LLMs.** Algorithm: cosine-similarity semantic retrieval over drug-label embeddings.
- **B. AI-Based Medication Safety Risk Detection and Personalized Alert Generation.** Algorithm: Focal Loss (from Jia et al. 2026).

My guide's requirement: the implementation must be an AI algorithm using deep learning, with scope for XAI. Dataset details must be ready for review.

## Rule 1: paper traceability (most important)

Every component, design choice and hyperparameter you implement must be labelled one of two ways:

- **FROM PAPERS**: name the paper (P1-P10 below) and the section, table or figure. Use only the facts listed under "Paper facts", or something you have actually read in a PDF in `papers/`.
- **NOT IN PAPERS**: your own design choice, or something from outside the ten papers.

Keep `aakaash/PAPER_TRACE.md` updated as you go, as a table with columns: component | file | source (paper + location, or NOT IN PAPERS) | note. Put a `# SOURCE: ...` comment at the top of every module. Never attribute something to a paper from memory. If you are not sure a paper says it, write "UNVERIFIED: check PDF". Your final message must print both lists, FROM PAPERS and NOT IN PAPERS.

## Rule 2: no invented numbers

Do not write a metric, count or file size in any document unless a script produced it from the real data in this session. A paper's numbers can be quoted only as "reported by <paper>", never as our result. Dataset counts in the report must come from `aakaash/data_report.py` output.

## Data (I download these; do not try to download them yourself)

- `data/dailymed_rx/`: DailyMed human prescription label zips (`dm_spl_release_human_rx_part1..6.zip`, about 3 GB each, part6 about 1.7 GB). Read straight from the zips and do not extract everything. The zips may be nested. Only some parts may be present at first, so the pipeline must loop over whatever parts exist.
- `data/mappings/`: DailyMed mapping files (SPL set id to RxNorm and other info), if present.
- `data/tac2017/`: `train_xml`, `gold_xml` and `unannotated_xml` (TAC 2017 labels; only the Adverse Reactions, Warnings and Precautions, and Boxed Warnings sections).
- `data/ddi2013/`: DDI Extraction 2013 corpus XML (train and test; DrugBank and MedLine).

If a folder is missing, stop that phase, tell me exactly what is missing, and continue with the other phases. Never substitute synthetic data silently. Before starting, check hardware (`nvidia-smi`, RAM, free disk) and tell me what you will adapt (smaller subset, CPU fallback, and so on).

## Working style

Use plan mode for Phase 0. Finish phases in order and stop with a short summary after each. Make small commits. Never modify or delete anything in `data/` or `papers/`. Run what you write and tell me honestly when something fails or is untested.

## Phases

### Phase 0: plan
Inspect the repo, the data and the hardware. Propose the file layout and ask me only questions that block progress.

### Phase 1: data pipeline and dataset report
- **Label parser** for SPL XML. Extract set id, title, active ingredient(s) (generic name), and the text of: Indications, Contraindications, Warnings and Precautions, Boxed Warning, Adverse Reactions, Drug Interactions, Use in Specific Populations. Look at real files before assuming the structure.
- **Section-aware chunking**: split by section first, then chunk (default 512 tokens with a small overlap, both configurable).
- **DDI 2013 parser**: one instance per drug pair per sentence, label from the pair's `type` attribute (effect, mechanism, advise, int; no interaction = false). Mask the two drug mentions with entity markers. Keep the official train/test split untouched and carve a dev set from train, stratified. Save as parquet or jsonl.
- **`data_report.py`** writes `DATASET_REPORT.md` with real counts: labels parsed, labels per section, chunks, distinct active ingredients, parse failures, DDI pairs per class per split, class imbalance ratios, and which DailyMed parts were loaded.

### Phase 2: Subarea A, retrieval and generic alternatives, with XAI
- **Embeddings**: default `llmrails/ember-v1`. If there is no GPU, use a smaller fallback and record which model was used.
- **Index**: FAISS over L2-normalised vectors (inner product equals cosine). Store chunk metadata: label id, section, ingredient, chunk id, text.
- **`retrieve(query, top_k=5, section=None)`** returns chunks with cosine scores and the source label and section. Support filtering by section.
- **`alternatives(drug_name)`**: resolve to the active ingredient, then return other labels or products with the same active ingredient. Use the RxNorm mapping file if it exists, otherwise normalised ingredient strings. Optional second mode: therapeutic neighbours via embedding similarity of Indications sections. Mark that one NOT IN PAPERS and label its output "similar indication, not interchangeable, needs clinician review".
- **No text generation needed today.** If an LLM answer is added later, it must be restricted to the retrieved passages and must cite the source id.
- **XAI (evidence-traceable output)**: every result shows source label, section, chunk text and score. Also add token-level attribution of why a chunk matched, using Integrated Gradients (Captum) on the query-chunk similarity, and save highlighted HTML. Mark the attribution NOT IN PAPERS.
- **Evaluation**: build a small test set of our own, for example precision@k of `alternatives()` on a set of ingredients, and checks that `retrieve()` returns the right section for questions like "pregnancy warning for X". State clearly that it is our own test, not from the papers. Use the TAC annotated labels to sanity-check section parsing.

### Phase 3: Subarea B, risk detection with Focal Loss, with XAI
- **Model**: BioBERT (`dmis-lab/biobert-base-cased-v1.1`) with entity markers, then a BiLSTM and a linear head (Jia's encoder). Do not implement the dual-graph network, cross-modal attention or BioGPT-GAN today. List them as future work.
- **Loss**: focal loss -alpha_t (1 - p_t)^gamma log(p_t) (Jia, Eq. 13). Provide a `--loss ce|focal` switch. Jia's equation is given but I did not find gamma or alpha values in what I read, so default to gamma = 2.0 and alpha from class frequencies, and flag both as NOT IN PAPERS.
- **Hyperparameters from Jia**: max sequence length 300, learning rate 5e-4, dropout 0.2, batch size 8, 20 epochs, two hidden layers of 256 units with ReLU. If fine-tuning BioBERT at 5e-4 diverges, use 2e-5 for the encoder and 5e-4 for the head, and record that as a deviation.
- **Metrics**: micro precision, recall and F1 over the four positive classes, ignoring false (Jia, Eq. 1-3), plus a per-class table (Jia, Table 3). Run the CE vs focal ablation, with 3 seeds if time allows.
- **Do not target Jia's 83.57% F1.** Their own Figure 2 confusion matrix implies roughly 40-45%. Report only what we measure, and note the discrepancy in the report.
- **XAI**: (1) an attention heatmap, inspired by Jia Fig. 5 (their weights come from the cross-modal attention module, ours would come from BERT or the BiLSTM, so it is a variant); (2) Integrated Gradients (Captum) token attributions for the predicted class; (3) deletion/insertion faithfulness checks (comprehensiveness and sufficiency). Items 2 and 3 are NOT IN PAPERS.
- **Personalized alert**: a deterministic template (no LLM) that combines the predicted interaction type, the highlighted evidence tokens, the retrieved Interactions and Warnings text for both drugs from Subarea A, and the patient profile fields (age, allergies, current medications, pregnancy). Severity tiers Critical/High/Advisory come from P10 (labels only). The rules for assigning a tier are NOT IN PAPERS.

### Phase 4: API skeleton (only if time remains)
FastAPI (built; the route names differ from the first plan, see README.md section 10), each route returning JSON that includes the evidence. The checker stores nothing: its medicine list is sent in the request body. Accounts, profile and medical history live in the local SQLite file `artifacts/app.db` (see WEBAPP_PLAN.md section 7). Enable CORS for the React dev server.

## Paper facts (the only things you may cite as FROM PAPERS)

- **P1, Gisladottir et al., Drug Safety 49:177-193 (2026).** DailyMed structured product labels (XML) as the source. Sections: Adverse Reactions, Warnings and Precautions, Boxed Warnings, Drug Interactions. TAC 2017 data: 101 train, 99 test, 2,208 unannotated labels. Embedding model `llmrails/ember-v1` (335M parameters, 1,024 dimensions), picked from the MTEB leaderboard. Cosine similarity thresholds: about 0.71 for term matching, 0.9 for mapping to RxNorm ingredients. Section lengths vary widely (Adverse Reactions median 7,701 characters).
- **P2, Heiler et al., Future Internet 18:139 (2026), MediChat.** RAG over patient leaflets. RecursiveCharacterTextSplitter with chunk size 1,100 and overlap 140. Chroma vector store. Cosine top-5. Llama 3.1 8B through Ollama at temperature 0.3. Prompt restricted to the retrieved leaflet text. Chunk ids built from source document and page. Evaluated with accuracy, precision, recall and F1 on yes/no questions.
- **P3, Zhou et al., Nature Biomedical Engineering 10:870-881 (2026), DrugGPT.** Three cooperating LLMs (inquiry analysis, knowledge acquisition, evidence generation). Retriever uses cosine similarity, top-3, chunk size 512. Disease-symptom-drug graph with MiniLM text embeddings and softmax-normalised cosine edge weights (temperature 0.1, top-K = 5). Prompting strategies: chain-of-thought, knowledge-consistency ("only use the knowledge provided") and evidence-traceable (return the source link). Evaluated on DDI-Corpus, ADE-Corpus-v2 and others.
- **P4, Bang et al., Korean DUR contraindication RAG (venue and year not visible in my copy).** Hybrid dense (cosine) plus BM25 retrieval with a re-ranker. `text-embedding-3-small`. Milvus. Chunks per contraindication entry, up to about 1,000 tokens, no overlap. GPT-4o mini. Evaluation by accuracy and F1 per category, plus a four-way grounding taxonomy (explicit or inferred, contraindicated or not).
- **P5, Li et al., npj Digital Medicine 9:433 (2026), EcoRxAgent.** Four-tool pipeline: candidate drug retrieval from a hospital formulary, candidate prescription generation, safety check, cost-effectiveness analysis. Outputs the top 5. Cost reduction ratio = (baseline cost - best cost) / baseline cost. Clinical data not public.
- **P6, Jia et al., iScience 29:115649 (2026), BIDGNN.** BioBERT, then BiLSTM, then dual graph (syntactic dependency graph from Stanza, and a similarity graph with threshold 0.7) with GCN layers, fused by cross-modal interactive attention, trained with focal loss. BioGPT-GAN augmentation (offline, 100% augmentation of positive classes, discriminator threshold 0.7). DDI Extraction 2013 with entity markers. Learning rate 5e-4, dropout 0.2, batch 8, 20 epochs, max length 300. Micro P/R/F1 over four positive classes. Class table in Table 1, per-class results in Table 3, attention visualisation in Fig. 5. Known inconsistency: reported 83.57% F1 vs the Fig. 2 confusion matrix.
- **P7, Sun et al., Int. J. Medical Informatics 220:106599 (2026).** Ontology mapping 12 education categories to package-insert sections. OAGLLM: sentence-level chunks, FAISS IndexFlatL2 for top-k candidates, cosine re-ranking, metadata filters from the ontology. Evaluation on six dimensions.
- **P8, Draelos et al., npj Digital Medicine 9:241 (2026).** HealthAdvice dataset (222 patient questions). Physician red-teaming: each response marked Acceptable or Problematic, with issue tags (Unsafe, Includes Problematic Content, Missing Important Info, Missing History Taking, Poor Writing) and a worst-case outcome note.
- **P9, Krifors et al., JAMIA Open 9(1) ooag004 (2026).** Classifier prompt plus critic prompt, run 3 times (6 outputs per case). Reliability = agreement proportion across the 6 outputs. Concordance with pharmacists measured.
- **P10, Shakarbaev, Int. J. Medical Informatics 215:106457 (2026).** Three-layer CDSS: rule-based alert engine, BioBERT-based NER, CatBoost severity triage (Critical / High / Advisory) that suppresses Advisory alerts from the active queue. This paper has internal inconsistencies, so use it only for the tier-labelling idea and never for numeric claims.

## Final report format

When you finish, give me:

1. What was built, in a few lines.
2. **FROM PAPERS**: component, paper, location.
3. **NOT IN PAPERS**: every own design choice.
4. What was not run or not verified.
5. The real numbers from `DATASET_REPORT.md` and from evaluation, with the commands to reproduce them.
