# Pinpoint

Pinpoint answers FastAPI questions using only FastAPI's own documentation, links the docs section each answer came from, and says "I don't know" when the docs do not cover the question. It runs fully on a local machine with Ollama, and it is measured against real questions people asked on the FastAPI forum.

**Headline result.** The same 3B model was given the same 20 docs questions with and without Pinpoint, and every answer was graded by hand. Alone, 12 of its 17 answers were wrong. With Pinpoint, 1 of 8 answers was wrong. On 20 questions the docs do not answer, Pinpoint says "I don't know" 16 times. These are small samples: one question is 5 points.

## Problem

Most questions on a library's forum are already answered in its docs, but people cannot find the answer, and support engineers answer the same questions every day. A chatbot that answers from the model's memory is not safe here: it invents flags, settings and install commands that look right. Pinpoint only answers from retrieved docs sections, cites them, refuses when they do not hold the answer, and measures how often it is right with real forum questions.

## What we built

| Part | What it does |
|---|---|
| Pinned docs | FastAPI docs at version 0.150.0 (156 Markdown pages, 465 example code files), so every result can be reproduced |
| Eval set | 350 real, answered questions from FastAPI's GitHub Discussions, each tagged |
| Chunker | Splits each docs page into sections and inlines the example code each section shows |
| Index | Turns every chunk into a vector with `nomic-embed-text` and stores it in ChromaDB |
| Search | Keyword search (BM25, written from scratch) and vector search, merged with Reciprocal Rank Fusion |
| Answer | A YES/NO check first decides whether the top 5 chunks answer the question. If yes, `llama3.2` answers and names the excerpts it used, and our code turns those into section links. Otherwise it returns "I don't know" |
| Eval harness | Runs a fixed sample of tagged questions end to end, grades them, and labels every failure by type |
| Model-alone baseline | The same questions with no retrieval, graded by hand |
| Telemetry | One structured trace per request; p50/p95 latency, tokens, refusal and error rates in every eval report |
| Semantic cache | A question almost identical to one already answered gets the saved answer |
| API | `POST /ask` with FastAPI, with Swagger UI at `/docs` |

## Run it

Needs Python 3.14 and [Ollama](https://ollama.com) with two models:

```
ollama pull llama3.2
ollama pull nomic-embed-text
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Clone the FastAPI docs at tag 0.150.0 into `data/fastapi-0.150.0` (only `docs/en/docs` and `docs_src` are used), then:

```
.venv\Scripts\python -m pinpoint_docs.chunk
.venv\Scripts\python -m pinpoint_docs.index
.venv\Scripts\python -m pinpoint_docs.answer How do I declare a request body?
.venv\Scripts\fastapi dev pinpoint_docs/api.py
.venv\Scripts\python -m scripts.run_eval
.venv\Scripts\python -m pytest -q
```

## Architecture

```
FastAPI docs 0.150.0 (Markdown + docs_src examples)
        |
        v
pinpoint_docs/chunk.py    split at # / ## / ### headings, inline code examples,
        |                 cut sections over 1500 chars at blank lines or bullets,
        |                 never inside a code block (longest chunk: 5576 chars, one code block)
        v
data/chunks.jsonl         2502 chunks: id, page, title, section, url, text
        |
        v
pinpoint_docs/index.py    nomic-embed-text (Ollama) -> ChromaDB, cosine distance
        |
        v
question --> embed (nomic-embed-text)
               |
               +--> answer cache: same settings and distance <= 0.03 -> saved answer
               |
               v
             pinpoint_docs/search.py
               BM25 top 50 ----+
                               +--> RRF --> top 5 chunks
               vector top 50 --+                |
                                                v
             pinpoint_docs/answer.py    check: "do these excerpts contain the answer?"
                                          NO  -> "I don't know." (no answer call)
                                          YES -> continue
                                                |
                                                v
                                        llama3.2, temperature 0, replies:
                                          EXCERPTS: 2, 4
                                          ANSWER: ...
                                                |
                                                v
                                        valid excerpt numbers -> answer + section links
                                        none, or "don't know"  -> "I don't know."
                                                |
                                                v
                                        data/traces.jsonl: one line per request
```

The eval harness calls the same `answer()` as a live question, so measured scores describe the system a user gets. The eval turns the answer cache off, so every question runs the full pipeline.

| File | Role |
|---|---|
| `pinpoint_docs/chunk.py` | Docs to chunks |
| `pinpoint_docs/index.py` | Chunks to ChromaDB |
| `pinpoint_docs/search.py` | BM25, RRF, MMR and hybrid search |
| `pinpoint_docs/answer.py` | Answer cache, YES/NO check, answer prompt, citation parsing, tracing |
| `pinpoint_docs/api.py` | FastAPI app: `POST /ask` |
| `scripts/collect_questions.py` | Collects answered questions from GitHub Discussions |
| `scripts/tag_questions.py` | Tool for tagging and reviewing questions |
| `scripts/compare_retrieval.py` | Compares chunking and search strategies |
| `scripts/run_eval.py` | Runs a fixed sample end to end and writes the report |
| `scripts/run_baseline.py` | Asks the model the same questions with no retrieval |
| `scripts/measure_threshold.py` | Tests whether a distance cutoff can spot questions the docs do not answer |
| `scripts/measure_gate.py` | Tests whether a YES/NO check can spot questions the excerpts do not answer |
| `scripts/m2_check.py` | The first 6 end-to-end questions |
| `evals/questions.json` | The 350 tagged questions |
| `evals/eval_llama3.2.json` | Latest eval run, one row per question with its trace id |
| `evals/eval_llama3.2_no-check.json` | Eval run before the YES/NO check |
| `evals/eval_llama3.2_graded.json` | The run whose answers were graded by hand |
| `evals/baseline_llama3.2.json` | Model-alone run |
| `evals/hand_grades.json` | Hand grades with a reason for each |
| `evals/split.json` | Frozen dev and test question ids |
| `scripts/make_split.py` | Builds the dev/test split |
| `evals/retrieval_results_dev.json` | Every chunking and search result on dev, with per-question ranks |
| `tests/` | pytest tests |

## RAG techniques

| Technique | In Pinpoint | Status |
|---|---|---|
| Structure-aware chunking | Split at Markdown headings, never inside a code block, with a size cap that fits the embedder's window | used, measured against fixed windows and whole pages |
| Contextual chunk headers | Page title is embedded with every chunk, and continuation pieces repeat their section name | used |
| Data cleaning | Example code inlined from `docs_src`, base64 blobs cut, forum template stripped from queries | used |
| Dense retrieval | `nomic-embed-text` with its `search_document:` / `search_query:` prefixes, stored in ChromaDB (HNSW, cosine) | used |
| Sparse retrieval | BM25 written from scratch, with an inverted index | used |
| Hybrid search + Reciprocal Rank Fusion | Top 50 from each retriever, merged by `1 / (60 + rank)` | used, measured |
| Metadata and citations | Every chunk carries page, section and a deep link. Answers cite excerpt numbers that our code maps to links, so a cited page always exists and was retrieved | used |
| Structured output | Model names its evidence before answering (`EXCERPTS:` then `ANSWER:`) | used, JSON tried and dropped |
| Abstention | A separate YES/NO call decides whether the excerpts answer the question before any answer is written | used, measured on two samples |
| Context budgeting | Top 5 chunks, about 5800 characters, inside an 8192-token window | used, measured |
| Deterministic generation | Temperature 0, pinned docs version, pinned eval set | used |
| Retrieval evaluation | hit@1, hit@5, MRR@10 on hand-checked questions, with a paired sign test | used |
| Answer evaluation | Correctness graded by hand against accepted forum answers | used for 40 answers. Automatic grading not built |
| Model-alone baseline | Same questions without retrieval | used |
| Per-request telemetry | Trace id, retrieved chunks and RRF scores, time per step, tokens, refusal and errors, as JSON lines | used |
| Semantic cache | Reuse the answer of an almost identical earlier question | used, with a strict cutoff measured below |
| Relevance threshold | Answer "I don't know" before calling the model when nothing retrieved is close enough | measured and rejected |
| MMR / diversity | Pick a top 5 that is relevant but not repetitive, from the top 20 | measured, no significant gain: on dev, hit@5 0.72 to 0.78 with weight 0.5 (5 questions better, 3 worse, p = 0.73), hit@1 0.42 to 0.40 |
| Reranking (cross-encoder) | Rescore the top 50 with a model that reads question and chunk together | not used yet: it targets the biggest failure (search misses). The top 10 holds a gold page for 78% of docs questions against 69% for the top 5, so there is room to gain |
| Query rewriting, multi-query, HyDE | Rewrite or expand the question before searching | not used: adds a model call per question, and the full question already ties with or beats the title alone |
| Parent-child (small-to-big) retrieval | Search small chunks, send their whole section | not used: sections are already the unit sent |
| Semantic chunking | Split where embedding similarity drops | not used: headings already mark topic changes in these docs |
| Agentic or multi-hop RAG | The model searches several times | out of scope |

## Results

**Read with care.** Two known problems in the numbers below are being fixed: most non-docs tags are unchecked drafts, and the docs questions used to choose the chunking and the YES/NO check are the same ones the eval reports on, which makes the scores look better than they are.

### Eval set

350 answered questions, newest first, collected on 2026-10-20.

| Tag | Count | Meaning |
|---|---|---|
| docs | 65 | The docs answer it. Each one is checked against the 0.150.0 docs and lists its gold pages |
| bug | 120 | About FastAPI, but the docs do not answer it |
| other-library | 81 | Really about Pydantic, Starlette, SQLAlchemy and so on |
| skip | 84 | Not a usable question |

Only 27 of the 350 accepted answers link to the docs site, so most gold pages were found by searching the docs by hand. 275 tags (all bug, other-library and skip tags except 10) are still drafts.

### Chunking and search strategies

`scripts/compare_retrieval.py` compares 5 chunking strategies and 3 search methods on the 40 dev docs questions. A hit means a chunk from a gold page is in the top 1 or the top 5. Context is the median number of characters in the top 5 chunks, which is what the model has to read. The query is the title plus the question's code and description. All rows, including title-only queries and MMR, are in `evals/retrieval_results_dev.json`.

| Chunking | Chunks | Search | hit@1 | hit@5 | MRR@10 | Context (chars) |
|---|---|---|---|---|---|---|
| Whole page | 155 | BM25 | 0.35 | 0.78 | 0.50 | 82718 |
| | | vector | 0.35 | 0.62 | 0.46 | 34696 |
| | | hybrid | 0.38 | **0.78** | 0.55 | 64579 |
| Fixed 1200-char windows | 1737 | BM25 | 0.38 | 0.60 | 0.48 | 6000 |
| | | vector | 0.38 | 0.62 | 0.49 | 6000 |
| | | hybrid | **0.50** | 0.72 | **0.61** | 6000 |
| Headings, no size cap | 2061 | BM25 | 0.33 | 0.50 | 0.42 | 9002 |
| | | vector | 0.47 | 0.68 | 0.56 | 5712 |
| | | hybrid | 0.42 | 0.70 | 0.54 | 7335 |
| **Headings, cap 1500 (chosen)** | 2502 | BM25 | 0.33 | 0.53 | 0.42 | 5945 |
| | | vector | 0.40 | 0.62 | 0.49 | 5258 |
| | | **hybrid (chosen)** | 0.42 | 0.72 | 0.54 | 5692 |
| | | hybrid + MMR 0.5 | 0.40 | **0.78** | 0.56 | 5648 |
| Headings, cap 3000 | 2177 | BM25 | 0.33 | 0.47 | 0.42 | 8320 |
| | | vector | 0.45 | 0.68 | 0.54 | 5552 |
| | | hybrid | 0.40 | 0.70 | 0.52 | 7248 |

With 40 questions, one question is worth 0.025, so each strategy was compared with the chosen one question by question, with a sign test:

| Against the chosen setup | hit@1 better / worse | hit@5 better / worse | p (hit@5) |
|---|---|---|---|
| BM25 alone | 2 / 6 | 0 / 8 | **0.01** |
| Vector alone | 3 / 4 | 1 / 5 | 0.22 |
| Fixed 1200-char windows, hybrid | 7 / 4 | 2 / 2 | 1.00 |
| Whole page, hybrid | 6 / 8 | 6 / 4 | 0.75 |
| Chosen setup + MMR 0.5 | 3 / 4 | 5 / 3 | 0.73 |
| Headings cap 3000, hybrid | 2 / 3 | 0 / 1 | 1.00 |

- **BM25 alone is clearly worse.** It is the only significant difference.
- **The other strategies are tied** with the chosen one, including fixed windows, which lead on hit@1 and MRR (0.61 against 0.54), and MMR, which leads on hit@5. Both leads are within noise.
- **Whole pages are ruled out.** The top 5 pages are about 65,000 characters, far more than the 8192-token window given to llama3.2.

Why headings with a 1500 cap plus hybrid search: its accuracy ties with the best, and it sends less text to the model than whole pages, no-cap headings or the 3000 cap. Its citations link to the exact section rather than just the page, and it never splits a code block.

The choice was first made on all 65 docs questions, which included the questions the eval reports on. It was then re-checked on the 40 dev questions only, with the same result.

### Eval run

`scripts/run_eval.py`, llama3.2, a fixed sample of 20 docs questions and 20 bug or other-library questions (seed 0). A docs question passes when the answer cites a gold page and does not say "I don't know"; any other question passes only on "I don't know". Passing does not mean correct: see the hand grades below.

| Measure | Before the YES/NO check | Final |
|---|---|---|
| Passed overall | 10 / 40 | **20 / 40** |
| Docs questions: search found a gold page in the top 5 | 12 / 20 | 12 / 20 |
| Docs questions: answer cited a gold page | **10 / 20** | 4 / 20 |
| Docs questions: wrongly said "I don't know" | 0 / 20 | 12 / 20 |
| Non-docs questions: correctly said "I don't know" | 0 / 20 | **16 / 20** |
| Passed by type: docs / bug / other-library | – | 4 / 20, 6 / 9, 10 / 11 |

Without the check, the model never says "I don't know": it always finds an excerpt to cite. With the check, Pinpoint passes twice as often overall, but answers far fewer docs questions. The check is not fully repeatable: between two runs on the same questions, 2 of 40 decisions flipped even at temperature 0.

### Pinpoint vs the model alone

`scripts/run_baseline.py` asks llama3.2 the same 40 questions with no retrieval. Its prompt also allows "I don't know." All 20 docs answers from both systems were read by hand against the accepted forum answer and the gold page. Each verdict and its reason are in `evals/hand_grades.json`.

| Docs questions (20) | Model alone | Pinpoint |
|---|---|---|
| Correct | 0 | **3** |
| Partly right | 5 | 4 |
| Wrong | 12 | **1** |
| Said "I don't know" | 3 | 12 |
| **Wrong among answers given** | **12 / 17 (71%)** | **1 / 8 (13%)** |
| Non-docs questions: said "I don't know" | 10 / 20 | 16 / 20 |

Alone, llama3.2 answers most docs questions, and most of those answers are wrong: invented flags, made-up install extras, code that does not run. Pinpoint answers fewer, but when it answers it is rarely wrong, and it always links the docs. Retrieval without the check made the model more overconfident than the model alone (0 against 10 refusals on non-docs questions), which is why the check exists. The grades come from one reader.

### Failure modes

The harness labels every failure. Counts from the latest run:

| Failure | Count | Stage | What happens |
|---|---|---|---|
| Search missed the gold page | **8** | search | No chunk from the right page in the top 5 |
| Refused although the gold page was found | 7 | YES/NO check | The check says NO to excerpts that hold the answer |
| Answered a question the docs do not cover | 4 | YES/NO check | The check says YES to related but not answering excerpts |
| Cited the wrong page | 1 | answer | Answered from an excerpt outside the gold pages |

Reading the answered docs questions by hand adds two more: answers that start right and then add wrong claims (4 partly right), and the right page with the wrong section, for example an answering section ranked 41st by search.

### Telemetry

Every call to `answer()` appends one JSON line to `data/traces.jsonl`: trace id, time, question, retrieved chunk ids and RRF scores, time for search, check and answer, prompt and output tokens, the answer, refusal, cache use and any error. Each eval row keeps its trace id. All runs are on a GTX 1650 (4 GB).

| Measure | Model alone | Before the check | Latest |
|---|---|---|---|
| Latency p50 | 6.3 s | 28.0 s | 24.1 s |
| Latency p95 | 13.1 s | 54.8 s | 38.6 s |
| Step p50: search / check / answer | – | 2.7 s / – / 25.4 s | 3.8 s / 12.6 s / 15.0 s |
| Prompt tokens per 1,000 questions | 680,000 | 2,358,000 | 2,841,000 |
| Output tokens per 1,000 questions | 93,000 | 145,000 | 55,000 |
| Answered / said "I don't know" | 27 / 13 | 40 / 0 | 12 / 28 |
| Errors | – | – | 0 / 40 |

24 s per question is the price of two calls to a local 3B model: one for the YES/NO check and one for the answer, each reading about 2,700 prompt tokens. The run before the check used an older GPU setup (part of the model on the CPU), so its latency is not directly comparable. All models run locally, so cost is reported in tokens, not money.

### Semantic cache cutoff

A cached answer is only safe if two different questions never fall inside the cutoff. Measured cosine distances between question embeddings:

| Pair | Distance |
|---|---|
| Same question, small rewording ("do I" / "can I", lower case, no question mark) | 0.002 – 0.007 |
| Same question, heavier rewording | 0.054 – 0.062 |
| Opposite meaning ("enable" / "disable", "required" / "optional", "async def" / "def") | 0.072 – 0.135 |
| Closest two different questions among the 266 tagged ones | 0.087 |

The cutoff is 0.03. Heavier rewordings miss the cache on purpose, because a wrong saved answer is worse than a slow right one. Cached answers are keyed on the model and on a hash of every setting that shapes an answer (prompts, check, top-k, model options), so changing any of them stops old answers from coming back. Rebuilding the index clears the cache.

### How the answer step was built

The first 6 end-to-end questions (`scripts/m2_check.py`) shaped the answer step. Search found a gold page for all 5 docs questions in every run, so each change targeted the model.

| Change | Passed | What it fixed or showed |
|---|---|---|
| First prompt, "cite like [2]" | 2 / 6 | Model skipped or invented citations |
| Stricter prompt | 2 / 6 | Rewording did not help |
| `qwen2.5:3b` instead of llama3.2 | 1 / 6 | Cited nothing |
| JSON output with required excerpt numbers | 4 / 6 | Citations became reliable, but answers stopped at the first `"` in code |
| `EXCERPTS:` / `ANSWER:` lines, 1500-char chunks | 4 / 6 | Kept the gain without the JSON quote problem |

Two ideas for "I don't know" were then tested with a bar set before each run:

- **Distance cutoff (rejected).** `scripts/measure_threshold.py` measured the closest-chunk distance for 65 docs and 201 non-docs questions: medians 0.201 and 0.210. Keeping 95% of docs questions would stop only 9% of the others. Embedding distance measures whether a question is about FastAPI, not whether the docs answer it.
- **YES/NO check (adopted).** `scripts/measure_gate.py` asked the model only "do these excerpts contain the answer?". It missed the first bar (85% YES on found-page docs questions), so it was retested on 40 new questions with a new bar set first (40% YES, 65% NO). Both samples agreed:

| Group | First sample (seed 0) | New sample (seed 1) |
|---|---|---|
| Docs questions where search found a gold page: YES | 6 / 12 (50%) | 8 / 17 (47%) |
| Docs questions where search missed: NO | 6 / 8 | 2 / 3 |
| Non-docs questions: NO | 16 / 20 (80%) | 17 / 20 (85%) |

## Problems and fixes

| Problem | Fix |
|---|---|
| `nomic-embed-text` in Ollama reads at most 2048 tokens and silently cuts off the rest. 18 chunks were longer, 15 of them on gold pages. A bigger `num_ctx` did not help: this build is fixed at 2048 | Sections are cut at blank lines or bullets, never inside a code block. The 1500-character limit was picked by the comparison above |
| An example file holds a 4269-character base64 image on one line | Code lines over 200 characters are shortened. Only this file was affected |
| Most accepted forum answers do not link the docs (27 of 350) | Gold pages were found by searching the docs by hand and checked one by one |
| Forum questions carry a long template full of checkboxes | Queries keep only the title, the example code and the description |
| A 3B model skips citations written as "cite like [2]" | The model names its evidence on an `EXCERPTS:` line, and our code builds the links |
| JSON output broke on the first `"` inside code | Plain two-line reply instead of JSON |
| llama3.2 copied the question's code back as its answer | The prompt says not to repeat the question's code |
| With retrieval, the model never said "I don't know" | Separate YES/NO check before answering, adopted after two measured samples |
| Citing a gold page does not mean the answer is right | 40 answers graded by hand against accepted answers |
| llama3.2 with an 8192-token window did not fit next to the embedder on a 4 GB GPU, so a third of it ran on the CPU and the two models pushed each other out of memory | llama3.2 is forced fully onto the GPU (`num_gpu` 99) and question embeddings run on the CPU (`num_gpu` 0), on purpose: the embedder is small, and keeping it off the GPU leaves room for the whole LLM. Answer time fell from 25.4 s to 15.0 s. Bulk indexing still uses the GPU |
| Several jobs on Ollama at once made one embedding take up to 60 seconds | One heavy job at a time |

## Limitations

- **Small samples.** The retrieval comparison uses 40 dev questions, and the test set has 25 docs questions. One question is 4 points in a group of 25. Only the BM25 result passed a significance test; the other differences, including MRR 0.54 against 0.61, are within noise.
- **Draft labels.** 275 of 350 tags are unchecked drafts, including most non-docs questions in the eval sample.
- **Tuned on the reported questions.** The chunking choice and the YES/NO check were chosen with the same docs questions the eval reports on.
- **One grader.** Correctness was graded by one person. The grades and reasons are in `evals/hand_grades.json` so they can be checked.
- **Answers few docs questions.** Pinpoint answers 8 of 20 docs questions. Search misses the gold page for 8 of 20, and the YES/NO check refuses 7 where the page was found.
- **The check is not fully repeatable.** 2 of 40 decisions flipped between runs at temperature 0.
- **Section-level misses are not measured.** Gold labels are pages, so a right page with the wrong section counts as found.
- **Small model, small GPU.** A 3B model on a 4 GB GPU misreads some excerpts that hold the answer, and a question takes 24 s at p50. A 7–8B model does not fit on this GPU.
- **Cache only helps repeats.** The 0.03 cutoff catches the same question with small rewording, not a new question on the same topic.
- **Scope.** One library, one docs version, English only, run locally.
