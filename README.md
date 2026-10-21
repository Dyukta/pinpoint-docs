# Pinpoint

Pinpoint answers FastAPI questions using only FastAPI's own documentation, links the docs section each answer came from, and says "I don't know" when the docs do not cover the question. It runs fully on a local machine with Ollama, and it is measured against real questions people asked on the FastAPI forum.

**Headline result.** The same 3B model was given the same 20 dev docs questions with and without Pinpoint, and every answer was graded by hand. Alone, 12 of its 17 answers were wrong. With Pinpoint, 1 of 8 answers was wrong. On 20 questions the docs do not answer, Pinpoint says "I don't know" 16 times. On 50 held-out test questions, all reviewed by hand, it passes 27. These are small samples: one question is 2 to 5 points.

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
| API | FastAPI: `POST /ask`, plus `GET /stats`, `/traces`, `/traces/{id}` and `/eval` for monitoring, with Swagger UI at `/docs` |
| Dashboard | React, Vite and Tailwind: ask questions, watch live latency, refusal, cache and error rates, open any trace, and see the held-out test results |

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

The dashboard needs Node 20 or newer. With the API running in one terminal:

```
cd dashboard
npm install
npm run dev
```

Then open http://localhost:5173. Vite forwards API calls to FastAPI on port 8000.

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
| `pinpoint_docs/api.py` | FastAPI app: `POST /ask` and the monitoring endpoints |
| `pinpoint_docs/stats.py` | Latency percentiles and rates from the traces, shared by the API and the eval |
| `dashboard/` | React + Vite + Tailwind monitoring dashboard |
| `scripts/collect_questions.py` | Collects answered questions from GitHub Discussions |
| `scripts/tag_questions.py` | Tool for tagging and reviewing questions |
| `scripts/compare_retrieval.py` | Compares chunking and search strategies |
| `scripts/run_eval.py` | Runs a fixed sample end to end and writes the report |
| `scripts/run_baseline.py` | Asks the model the same questions with no retrieval |
| `scripts/measure_threshold.py` | Tests whether a distance cutoff can spot questions the docs do not answer |
| `scripts/measure_gate.py` | Compares YES/NO check variants on a split |
| `pinpoint_docs/rerank.py` | Cross-encoder reranker on ONNX Runtime (measured, not used) |
| `scripts/measure_rerank.py` | Measures reranking on a split |
| `scripts/judge.py` | LLM judge for faithfulness, relevancy and correctness, compared with the hand grades |
| `scripts/m2_check.py` | The first 6 end-to-end questions |
| `evals/questions.json` | The 350 tagged questions |
| `evals/eval_test_llama3.2.json` | Held-out test run, one row per question with its trace id |
| `evals/eval_llama3.2.json` | Latest dev-sample run |
| `evals/eval_test_no-check_llama3.2.json` | Held-out test run with the YES/NO check turned off |
| `evals/eval_llama3.2_no-check.json` | Dev-sample run before the YES/NO check |
| `evals/m2_answers_llama3.2.json`, `evals/m2_answers_qwen2.5-3b.json` | The first 6 end-to-end questions, answered by each model |
| `evals/gate_dev.json` | Per-question votes of the YES/NO check variants on dev |
| `evals/rerank_dev.json` | Per-question ranks with and without reranking on dev |
| `evals/eval_llama3.2_graded.json` | The run whose answers were graded by hand |
| `evals/baseline_llama3.2.json` | Model-alone run |
| `evals/hand_grades.json` | Hand grades for correctness, faithfulness and relevancy, with a reason for each |
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
| Abstention | A separate YES/NO call decides whether the excerpts answer the question before any answer is written | used: chosen on dev, then 27 against 15 passes on the held-out test (p = 0.02) |
| Context budgeting | Top 5 chunks, about 5800 characters, inside an 8192-token window | used, measured |
| Deterministic generation | Temperature 0, pinned docs version, pinned eval set | used |
| Retrieval evaluation | hit@1, hit@5, MRR@10 on hand-checked questions, with a paired sign test | used |
| Answer evaluation | Correctness against accepted forum answers, faithfulness to the excerpts and relevancy to the question | graded by hand for 40 answers; an LLM judge is being calibrated against these grades |
| Model-alone baseline | Same questions without retrieval | used |
| Per-request telemetry | Trace id, retrieved chunks and RRF scores, time per step, tokens, refusal and errors, as JSON lines | used |
| Semantic cache | Reuse the answer of an almost identical earlier question | used, with a strict cutoff measured below |
| Relevance threshold | Answer "I don't know" before calling the model when nothing retrieved is close enough | measured and rejected |
| MMR / diversity | Pick a top 5 that is relevant but not repetitive, from the top 20 | measured, no significant gain: on dev, hit@5 0.72 to 0.78 with weight 0.5 (5 questions better, 3 worse, p = 0.73), hit@1 0.42 to 0.40 |
| Reranking (cross-encoder) | Re-sort the top 20 with a model that reads question and chunk together | measured and rejected: `ms-marco-MiniLM-L6-v2` lowered hit@5 on dev from 29 to 25 or 28 and added 2.7 s |
| Query rewriting, multi-query, HyDE | Rewrite or expand the question before searching | not used: adds a model call per question, and the full question already ties with or beats the title alone |
| Parent-child (small-to-big) retrieval | Search small chunks, send their whole section | not used: sections are already the unit sent |
| Semantic chunking | Split where embedding similarity drops | not used: headings already mark topic changes in these docs |
| Agentic or multi-hop RAG | The model searches several times | out of scope |

## Results

### Eval set and split

350 answered questions, newest first, collected on 2026-10-20. Only 27 of the accepted answers link to the docs site, so most gold pages were found by searching the docs.

| Tag | Count | Meaning |
|---|---|---|
| docs | 68 | The 0.150.0 docs answer it; lists its gold pages |
| bug | 119 | About FastAPI, but the docs do not answer it |
| other-library | 79 | Really about Pydantic, Starlette, Uvicorn and so on |
| skip | 84 | Not a usable question |

The questions are split once, in `evals/split.json`, before any final number was measured:

- **dev, 80 questions** (40 docs, 40 non-docs): every question already used for a decision, namely the two samples behind the YES/NO check. Chunking, search and the check are tuned only on dev.
- **test, 50 questions** (28 docs, 22 non-docs): never used for a decision. Final numbers are reported only on test.

How each tag was checked:

| Status | Count | Meaning |
|---|---|---|
| human-reviewed | 50 | Every test question, reviewed by the author against the 0.150.0 docs |
| human | 11 | Tagged by the author from the start |
| reviewed | 36 | Dev non-docs questions, re-read against the question, the accepted answer and the docs in a second pass, not by the author |
| checked | 39 | Docs questions checked against the docs by an automated pass, not by a person (37 of them in dev) |
| draft | 214 | Not used by any eval |

Reviewing the test set moved 3 questions from non-docs to docs (the docs answer them through a section the forum answer did not link) and narrowed one gold page.

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

### Held-out test results

`scripts/run_eval.py test`, llama3.2, the 50 test questions. A docs question passes when the answer cites a gold page and does not say "I don't know"; any other question passes only on "I don't know". Passing does not mean correct: see the hand grades below.

| Measure | Current YES/NO check |
|---|---|
| Passed overall | **27 / 50** |
| Docs questions: search found a gold page in the top 5 | 17 / 28 |
| Docs questions: answer cited a gold page | 9 / 28 |
| Docs questions: wrongly said "I don't know" | 14 / 28 |
| Non-docs questions: correctly said "I don't know" | **18 / 22** |
| Passed by type: docs / bug / other-library | 9 / 28, 12 / 16, 6 / 6 |

| Failure on test | Count | Stage |
|---|---|---|
| Search missed the gold page | **11** | search |
| Refused although the gold page was found | 7 | YES/NO check |
| Answered a question the docs do not cover | 4 | YES/NO check |
| Cited the wrong page | 1 | answer |

On test, search misses are the largest failure. On dev it was the other way round (15 refusals against 11 misses), and the fixes below were chosen on dev, as they must be.

**The adopted fix, measured on held-out questions.** The YES/NO check was chosen on dev. Running the same 50 test questions with the check turned off (`scripts/run_eval.py test no-check`) gives a clean before and after:

| Test, 50 questions | Without the check | With the check |
|---|---|---|
| Passed overall | 15 / 50 | **27 / 50** |
| Docs questions: answer cited a gold page | **15 / 28** | 9 / 28 |
| Non-docs questions: correctly said "I don't know" | 0 / 22 | **18 / 22** |
| Answers given | 50 | 18 |
| Answers that cite a gold page | 15 / 50 (30%) | **9 / 18 (50%)** |
| Latency p50 / p95 | 18.3 s / 30.6 s | 19.1 s / 42.2 s |

Question by question, the check is better on 18 and worse on 6 (sign test p = 0.02), the only significant result on the test set. Without it, the model answers all 50 questions, including every question the docs do not cover. With it, Pinpoint answers fewer questions, but half of its answers cite the right page instead of under a third, at the cost of 6 docs answers it now refuses.

### Development results

These come from the 40-question seed 0 sample, which is now part of dev. They shaped the system, so they are more optimistic than the test numbers.

**Adding the YES/NO check:**

| Measure (dev sample) | Before the check | After |
|---|---|---|
| Passed overall | 10 / 40 | **20 / 40** |
| Docs questions: answer cited a gold page | **10 / 20** | 4 / 20 |
| Docs questions: wrongly said "I don't know" | 0 / 20 | 12 / 20 |
| Non-docs questions: correctly said "I don't know" | 0 / 20 | **16 / 20** |

Without the check, the model never says "I don't know": it always finds an excerpt to cite. The check is not fully repeatable: between two runs on the same questions, 2 of 40 decisions flipped even at temperature 0.

**Pinpoint against the model alone.** `scripts/run_baseline.py` asks llama3.2 the same questions with no retrieval; its prompt also allows "I don't know." All 20 docs answers from both systems were read by hand against the accepted forum answer and the gold page (`evals/hand_grades.json`).

| Docs questions (20) | Model alone | Pinpoint |
|---|---|---|
| Correct | 0 | **3** |
| Partly right | 5 | 4 |
| Wrong | 12 | **1** |
| Said "I don't know" | 3 | 12 |
| **Wrong among answers given** | **12 / 17 (71%)** | **1 / 8 (13%)** |
| Non-docs questions: said "I don't know" | 10 / 20 | 16 / 20 |

Alone, llama3.2 answers most docs questions, and most of those answers are wrong: invented flags, made-up install extras, code that does not run. Retrieval without the check made the model more overconfident than the model alone (0 against 10 refusals on non-docs questions), which is why the check exists.

**Faithfulness and relevancy.** Each of the 12 answers Pinpoint gave was also graded by hand, before any automatic judge was run: is every claim and code line backed by the 5 excerpts it was given, and does it address what was asked?

| 12 answers | Yes | Partly | No |
|---|---|---|---|
| Faithful to the excerpts | 3 | 7 | 2 |
| Relevant to the question | 5 | 5 | 2 |

Citations are always real, because the code builds them, but the answer text often mixes in claims from the question or the model's memory: a function name the asker mentioned, "fixed in Python 3.13", one invented link. This is the clearest remaining hallucination problem.

### Telemetry

Every call to `answer()` appends one JSON line to `data/traces.jsonl`: trace id, time, question, retrieved chunk ids and RRF scores, time for search, check and answer, prompt and output tokens, the answer, refusal, cache use and any error. Each eval row keeps its trace id. All runs are on a GTX 1650 (4 GB).

| Measure | Model alone (dev) | Before the check (dev) | Current (test) |
|---|---|---|---|
| Latency p50 | 6.3 s | 28.0 s | 19.1 s |
| Latency p95 | 13.1 s | 54.8 s | 42.2 s |
| Step p50: search / check / answer | – | 2.7 s / – / 25.4 s | 3.2 s / 12.8 s / 15.9 s |
| Prompt tokens per 1,000 questions | 680,000 | 2,358,000 | 2,887,000 |
| Output tokens per 1,000 questions | 93,000 | 145,000 | 58,000 |
| Answered / said "I don't know" | 27 / 13 | 40 / 0 | 18 / 32 |
| Errors | – | – | 0 / 50 |

About 20 s per question is the price of two calls to a local 3B model: one for the YES/NO check and one for the answer, each reading about 2,700 prompt tokens. Questions the check refuses skip the answer call. The run before the check used an older GPU setup (part of the model on the CPU), so its latency is not directly comparable. All models run locally, so cost is reported in tokens, not money.

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

### Fixing refusals

The YES/NO check is the largest failure on the dev questions: it says NO for 15 of the 29 dev docs questions where search found the gold page, while a perfect reranker over the top 20 could recover at most 7 search misses. Two changes to the check are measured on dev with `scripts/measure_gate.py`, against the current check run under the same conditions:

- **Fully or in part:** ask whether the excerpts contain information that answers the question fully or in part, instead of whether they contain the answer.
- **No code:** give the check only the question's title and description, without the asker's code.

Bar set before the run: adopt a change if it says YES for at least 5 more of the 29 found-page dev docs questions than the current check, and still says NO for at least 70% of the 40 dev non-docs questions. The adopted check is then compared with the current one on the test questions only.

| Variant (80 dev questions) | Found-page docs: YES | Missed docs: NO | Non-docs: NO | Result |
|---|---|---|---|---|
| Current check | 13 / 29 | 7 / 11 | 32 / 40 (80%) | baseline |
| Fully or in part | **18 / 29** | 7 / 11 | 13 / 40 (33%) | rejected: says YES to almost everything |
| No code | 16 / 29 | 8 / 11 | 29 / 40 (73%) | rejected: 3 more YES, the bar was 5 |

Neither change passed, so the check is unchanged. A looser question makes the 3B model agree with almost anything, and hiding the asker's code helps only a little. Per-question results are in `evals/gate_dev.json`.

### Reranking

With the check unchanged, the next fix targets search misses, the largest failure on test. A cross-encoder (`cross-encoder/ms-marco-MiniLM-L6-v2`, run with ONNX Runtime on the CPU) reads the question and each chunk together and re-sorts the top 20 chunks from hybrid search. It is measured on the 40 dev docs questions with `scripts/measure_rerank.py`, with two forms of the question: the full question, and the title and description without the asker's code.

Bar set before the run: adopt reranking if it puts a gold page in the top 5 for at least 4 more of the 40 dev docs questions than hybrid search alone, and adds at most 2 seconds per question. The adopted version is then compared with the current pipeline on the test questions only.

| Search (40 dev docs questions) | hit@1 | hit@5 | Against hybrid at hit@5 | Added time (p50) |
|---|---|---|---|---|
| Hybrid | 17 | **29** | – | – |
| Hybrid + rerank, full question | 15 | 25 | 1 better, 5 worse (p = 0.22) | 2.8 s |
| Hybrid + rerank, no code | 17 | 28 | 2 better, 3 worse (p = 1.00) | 2.7 s |

Rejected: reranking made search slightly worse and slower. This cross-encoder was trained on short web-search queries (MS MARCO), not on long forum posts full of code matched against technical docs. A reranker trained on code or documentation might do better; it was not tried. Per-question results are in `evals/rerank_dev.json`.

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

- **Small samples.** The retrieval comparison uses 40 dev questions, and the test set has 28 docs and 22 non-docs questions. One question is about 4 points in a group of 25. Only the BM25 result passed a significance test; the other differences, including MRR 0.54 against 0.61, are within noise.
- **Labels.** The 50 test questions were reviewed by the author. The dev questions were reviewed by a second pass, not by the author. 214 questions that no eval uses are still drafts.
- **Dev numbers are optimistic.** The chunking and the YES/NO check were chosen on dev questions, so only the test numbers are unbiased.
- **One grader.** Correctness was graded by one person. The grades and reasons are in `evals/hand_grades.json` so they can be checked.
- **Answers few docs questions.** On test, Pinpoint cites a gold page for 9 of 28 docs questions. Search misses the gold page for 11, and the YES/NO check refuses 7 where the page was found.
- **Answers are not fully faithful.** Only 3 of 12 hand-graded answers were backed by their excerpts in every claim. Citations are always real; the answer text is not always.
- **The check is not fully repeatable.** 2 of 40 decisions flipped between runs at temperature 0.
- **Section-level misses are not measured.** Gold labels are pages, so a right page with the wrong section counts as found.
- **Small model, small GPU.** A 3B model on a 4 GB GPU misreads some excerpts that hold the answer, and a question takes 24 s at p50. A 7–8B model does not fit on this GPU.
- **Cache only helps repeats.** The 0.03 cutoff catches the same question with small rewording, not a new question on the same topic.
- **Scope.** One library, one docs version, English only, run locally.
