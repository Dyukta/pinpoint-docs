# Pinpoint

**A RAG system that answers FastAPI questions only from FastAPI's own docs, links the exact section it used, and says "I don't know" when the docs do not cover the question. It runs fully on a laptop GPU and is measured on real questions from the FastAPI forum.**

## Results

| | |
|---|---|
| **Fewer wrong answers** | On 20 hand-graded docs questions, the model alone was wrong in 12 of its 17 answers (71%). With Pinpoint, 1 of 8 (13%). |
| **Knows when to stop** | On 22 held-out questions the docs do not answer, Pinpoint says "I don't know" 18 times. Without its abstention check, 0 times. |
| **Measured on held-out data** | The abstention check was chosen on dev questions, then tested on 50 held-out, hand-reviewed questions: 27 passed with it, 15 without (sign test p = 0.02). |
| **Runs locally** | 3B model on a 4 GB GTX 1650: p50 19 s, p95 42 s per question, 0 errors in 50. No paid APIs. |

The samples are small (one question is 2 to 5 points), and every number comes from a script and a saved result file. The full record is in [evals/REPORT.md](evals/REPORT.md).

## Problem

Most questions on a library's forum are already answered in its docs, but people cannot find the answer. A chatbot that answers from memory is not safe here: it invents flags, settings and install commands that look right. Pinpoint answers only from retrieved docs sections, cites them, refuses when they do not hold the answer, and proves how often it is right.

## Tech stack

Python 3.14 · FastAPI · Ollama (`llama3.2`, `nomic-embed-text`) · ChromaDB · BM25 written from scratch · ONNX Runtime · React 19 · Vite · Tailwind CSS · pytest

## Architecture

```
FastAPI docs 0.150.0 ──> chunk at headings (2,502 chunks, code blocks kept whole)
                    ──> nomic-embed-text ──> ChromaDB (HNSW, cosine)

question ──> answer cache (near-identical question, same settings) ──> saved answer
         ──> BM25 top 50 ─┐
                          ├─> Reciprocal Rank Fusion ──> top 5 sections
         ──> vector top 50┘                                   │
                                                              v
                              YES/NO check: "do these sections answer it?"
                                 NO  ──> "I don't know."
                                 YES ──> llama3.2 answers, names the sections it used
                                         ──> code turns them into docs links
                                                              │
                                                              v
                              trace per request ──> /stats, /traces ──> dashboard
```

The evaluation calls the same `answer()` function as a live user, so the measured scores describe the system people actually get.

## What's inside

| Technique | How Pinpoint uses it |
|---|---|
| Structure-aware chunking | Splits pages at Markdown headings, never inside a code block, with a size cap measured against the embedder's 2,048-token limit |
| Hybrid search | Keyword search (BM25) and vector search, merged with Reciprocal Rank Fusion. BM25 alone was significantly worse (p = 0.01) |
| BM25 from scratch | About 30 lines with an inverted index and a tokenizer that keeps `response_model` as one token. At 2,502 chunks a library would add a dependency, not speed |
| Grounded citations | The model only names excerpt numbers; code builds the links, so every cited page exists and was retrieved |
| Abstention | A separate YES/NO call decides whether to answer before any answer is written |
| Semantic cache | Reuses the answer to a near-identical question; the cutoff was set from measured distances between real questions, and entries are keyed on a hash of every setting |
| Telemetry | One structured trace per request: retrieved chunks and scores, time per step, tokens, refusals, errors |
| Monitoring | FastAPI endpoints for live stats and traces, and a React dashboard to ask questions, watch latency and refusal rates, and open any trace |
| Evaluation | 350 real forum questions, a frozen dev/test split, hand grades for correctness, faithfulness and relevancy, a no-retrieval baseline, and sign tests |

## Tried, measured, rejected

Every experiment had its pass mark written down before it ran, on dev questions only.

| Idea | Result |
|---|---|
| Distance cutoff for "I don't know" | Rejected: embedding distance tells whether a question is about FastAPI, not whether the docs answer it |
| Cross-encoder reranker (`ms-marco-MiniLM-L6-v2`) | Rejected: top-5 hits fell from 29 of 40 to 25 (28 without the asker's code), and each question took about 2.7 s longer |
| Softer YES/NO question | Rejected: the 3B model then said YES to two thirds of unanswerable questions |
| MMR for more varied results | Rejected: no significant gain |
| llama3.2 as an automatic grader | Rejected: agreed with the hand grades on as few as 1 of 8 answers |
| JSON output for citations | Replaced: answers broke at the first quote in code |

## Monitoring dashboard

A React, Vite and Tailwind dashboard in `dashboard/` reads the API: an "Ask the docs" box, live p50/p95 latency, refusal, cache and error rates, a clickable list of traces showing what was retrieved and how long each step took, and the held-out test results.

## Limitations

- **Small samples.** 50 held-out questions; most differences other than the two significant ones are within noise.
- **Answers few docs questions.** On test it cites the right page for 9 of 28 docs questions: search misses 11, and the check refuses 7 it could have answered.
- **Not fully faithful.** Only 3 of 12 hand-graded answers were backed by their sources in every claim. The links are always real; the text is not always.
- **Small model.** A 3B model on a 4 GB GPU; a 7–8B model does not fit.
- **One grader, one library.** Hand grades come from one person, and only FastAPI 0.150.0 in English is covered.

## Project layout

| Folder | Contents |
|---|---|
| `pinpoint_docs/` | Chunking, indexing, search, answering, stats and the FastAPI app |
| `dashboard/` | React + Vite + Tailwind monitoring dashboard |
| `scripts/` | Question collection, tagging, evaluation, baseline and experiment scripts |
| `evals/` | Tagged questions, the dev/test split, every result file, and [REPORT.md](evals/REPORT.md) |
| `tests/` | pytest tests |
