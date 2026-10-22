# Pinpoint

RAG over the FastAPI docs. You ask a FastAPI question, it answers only from the docs, links the section it used, and says "I don't know" when the docs don't cover it. Runs locally on a GTX 1650 (4 GB) with Ollama, and I evaluate it on real questions from the FastAPI GitHub Discussions.

## Results

- Model alone vs Pinpoint, 20 docs questions graded by hand: the model alone got 12 of its 17 answers wrong. Pinpoint got 1 of 8 wrong (it said "I don't know" to the rest).
- On 22 held-out questions the docs don't answer, Pinpoint says "I don't know" 18 times. Without the YES/NO check it never does.
- The check was picked on dev data, then tested once on 50 held-out questions: 27 pass with it, 15 without (sign test p = 0.02).
- Latency on 80 dev questions went from 22.8 s to 8.2 s p50 (53.5 s to 18.9 s p95) with 43 passes vs 44 before.

The samples are small, so one question moves a score by 2 to 5 points. Every number here comes from a script and a result file in `evals/`. The held-out numbers are from before the speed work; I'll rerun the test set once with the final setup.

## Why

Most questions on a library's forum are already answered somewhere in its docs. A chatbot answering from memory is risky for this: it makes up flags, settings and install commands that look plausible. So Pinpoint only answers from docs sections it retrieved, cites them, and refuses when they don't contain the answer.

## Stack

Python 3.14, FastAPI, Ollama (`llama3.2` and `nomic-embed-text`), Gemini Flash as an optional hosted model, ChromaDB, BM25 (my own, about 30 lines), React 19 + Vite + Tailwind for the dashboard, pytest, Docker, GitHub Actions.

## How it works

```
FastAPI docs 0.150.0 -> split at headings (2,502 chunks, code blocks never split)
                     -> nomic-embed-text -> ChromaDB

question -> answer cache (same question, same settings) -> cached answer
         -> BM25 top 50   -+
                           +-> Reciprocal Rank Fusion -> top 3 sections
         -> vector top 50 -+                               |
                                                           v
                             YES/NO check: do these sections answer it?
                               NO  -> "I don't know."
                               YES -> same chat continues, llama3.2 answers
                                      and lists the excerpt numbers it used
                                      -> code turns those into docs links
                                                           |
                                                           v
                             one trace per request -> /stats, /traces -> dashboard
```

A few details:

- The model never writes URLs. It only returns excerpt numbers, and the code maps them to links, so a cited page always exists and was actually retrieved.
- The eval calls the same `answer()` function the API uses, so the scores are for the real pipeline.
- BM25 is hand-written with an inverted index and a tokenizer that keeps `response_model` as one token. At 2,502 chunks a library would just add a dependency.
- The answer cache only matches near-identical questions (cosine distance 0.03 or less). Two different real questions were never closer than 0.087. Cache entries are keyed on a hash of every setting, so changing a prompt invalidates them.
- Each trace has the retrieved chunks and scores, time per step, and for every model call the tokens plus load, read and write time.
- Answers stream to the dashboard word by word over Server-Sent Events, and closing the page stops the model (see "Running it as a service").

## Evaluation

I collected 350 answered questions from GitHub Discussions (2026-10-20) and tagged each one: `docs` (the 0.150.0 docs answer it, with gold pages), `bug` (about FastAPI but not in the docs), `other-library` (really about Pydantic, Starlette, etc.) or `skip`. Then I froze a split:

- dev, 80 questions (40 docs, 40 not). All tuning happens here.
- test, 50 questions (28 docs, 22 not), all reviewed by me. Not used for any decision.

A docs question passes if the answer cites a gold page. Any other question passes only if it says "I don't know". Passing doesn't mean the answer is correct, so I also graded answers by hand.

### YES/NO check on the test set

| Test, 50 questions | No check | With check |
|---|---|---|
| Passed | 15 | 27 |
| Docs: cited a gold page | 15 / 28 | 9 / 28 |
| Not in docs: said "I don't know" | 0 / 22 | 18 / 22 |
| Answers that cite a gold page | 15 / 50 | 9 / 18 |

Per question the check wins 18 and loses 6 (p = 0.02). Without it the model answers all 50, including every question the docs don't cover. The cost is 6 docs answers it now refuses.

### On questions it has never seen

To check the "I don't know" side isn't tuned to dev, `scripts/run_eval.py fresh` draws 40 random questions from the ones no split uses (all of them out of scope for the docs) and prints the seed so the draw can be repeated. With seed 8034 it said "I don't know" to 33 of 40, against 34 of 40 on dev, at the same speed (p50 8.5 s). Of the 7 it answered, I'd call about 4 wrong and 3 partly covered by the docs. Those labels are drafts I haven't reviewed, so a few "out of scope" questions are really answerable.

The check is also repeatable now: across two dev runs, the 63 questions whose top 3 excerpts didn't change got the same YES or NO all 63 times. An older setup flipped 2 of 40.

### Hand grades, 20 docs questions

| | Model alone | Pinpoint |
|---|---|---|
| Correct | 0 | 3 |
| Partly right | 5 | 4 |
| Wrong | 12 | 1 |
| "I don't know" | 3 | 12 |

I also checked each of Pinpoint's 12 answers against the excerpts it was given. Only 3 were fully backed by them, 7 partly, 2 not. The links are always real but the text sometimes pulls in things from the question or from the model's memory.

### Search

I tried 5 ways of chunking the docs with 3 search methods on the 40 dev docs questions.

Chunking:
- whole page: one chunk per page
- fixed windows: every 1,200 characters, wherever that lands
- headings, no cap: one chunk per `#`/`##`/`###` section
- headings, cap 1,500: long sections split at blank lines or bullets, never inside a code block
- headings, cap 3,000: same with a bigger cap

Search:
- BM25: keyword matching
- vector: `nomic-embed-text` embeddings, closest chunks win
- hybrid: top 50 from each, merged with RRF (`1 / (60 + rank)`)

hit@5 = share of questions with a gold-page chunk in the top 5. Context = median characters in the top 5, which is what the model has to read.

| Chunking | Chunks | BM25 | Vector | Hybrid | Hybrid context |
|---|---|---|---|---|---|
| Whole page | 155 | 0.78 | 0.62 | 0.78 | 64,579 |
| Fixed 1,200 | 1,737 | 0.60 | 0.62 | 0.72 | 6,000 |
| Headings, no cap | 2,061 | 0.50 | 0.68 | 0.70 | 7,335 |
| Headings, cap 1,500 (used) | 2,502 | 0.53 | 0.62 | 0.72 | 5,692 |
| Headings, cap 3,000 | 2,177 | 0.47 | 0.68 | 0.70 | 7,248 |

BM25 alone was the only significantly worse option (0 better, 8 worse vs the chosen setup, p = 0.01). The rest are within noise. Whole pages don't fit: the top 5 are about 65,000 characters, way past the 8,192-token window. I went with headings + 1,500 cap + hybrid because it ties on accuracy, sends the least text, and links to the exact section.

## Speeding it up

It started at 22.8 s p50 on dev, with some questions taking over 50 s. Before changing anything I wrote down the goal: p50 at most 10 s on dev, and no fewer than the 44 passes it had.

| Dev, 80 questions | Before | After |
|---|---|---|
| p50 / p95 | 22.8 s / 53.5 s | 8.2 s / 18.9 s |
| search / check / answer (p50) | 3.3 / 13.7 / 15.0 s | 0.9 / 6.7 / 2.2 s |
| Prompt tokens per 1,000 questions | 2.69M | 1.95M |
| Passed | 44 | 43 |

First I added timing to the traces: for each model call, how long Ollama spent loading the model, reading the prompt and writing the reply. Writing was about 1 s. Nearly everything else was reading. Then, one by one:

1. **2 s lost on every Ollama call.** My timer said 8.2 s for a call Ollama itself timed at 5.8 s. A request to `localhost` took 2.06 s, to `127.0.0.1` 0.01 s. On Windows Python tries IPv6 (`::1`) first and Ollama only listens on IPv4. Switched to `127.0.0.1`: about 6 s saved per question, search went from 3.3 s to 0.9 s.
2. **Model reloads.** Ollama unloads a model after 5 idle minutes, and the next question paid 4 to 13 s to load it. Now the requests ask Ollama to keep the models loaded.
3. **The excerpts were read twice.** The check and the answer each read about the same prompt, around 7 s each (this GPU reads about 200 tokens/s). I made the answer a follow-up message in the check's chat. The answer prompt now starts with the check prompt, Ollama reuses what it already read, and reading for the answer dropped to under 1 s.
4. **My first try at #3 broke the check.** I had given both calls one shared system prompt ("You answer FastAPI questions..."). The check started saying YES to 26 of 40 out-of-scope questions instead of 7, and passes fell to 33. A more neutral wording got 31. The 3B model only stays strict with its original check prompt, so I kept that prompt word for word and shared it by continuing the chat instead.
5. **Top 3 excerpts instead of 5.** The question is about 400 tokens and the 5 excerpts about 1,460, so this cuts about 600 tokens (around 3 s). The cost: a gold page is in the top 3 for 25 of 40 dev docs questions vs 29 in the top 5.
6. **One run was way slower than the rest.** The Ollama log showed another project loading `qwen2.5:3b` on the same 4 GB GPU, so the two models kept evicting each other. I reran it with nothing else on Ollama.

The speed goal was met but I missed the pass goal by one (43 vs 44). Per question, 7 were lost and 6 gained, so that's noise (p = 1.0). Two of the lost ones had their gold page at rank 4, which isn't sent anymore. I kept the change and I'm noting the miss here rather than changing the goal after the fact.

The runs are in `evals/eval_dev_before-speed_llama3.2.json`, `eval_dev_shared-prompt_llama3.2.json`, `eval_dev_neutral-k3_llama3.2.json`, and `eval_dev_llama3.2.json` (final).

## Running it as a service

**Streaming.** `POST /ask/stream` sends Server-Sent Events: a `status` event for each step (search, check, answer), a `token` event for each piece of the answer, and a `done` event with the final answer and its links. The model writes `EXCERPTS: 2, 4` before `ANSWER:`, so only the text after `ANSWER:` is streamed. The links are still built by code at the end. `respond()` is a generator that yields these events, and the non-streaming `answer()` used by `POST /ask` and the eval just runs it to the end, so there is one pipeline, not two. On a live question the first word showed up at 4.1 s and the whole answer at 6.0 s.

**Cancelling.** If the client goes away, the endpoint sets a cancel flag. A worker thread always runs the pipeline to the end, sees the flag at the next event, closes the stream to Ollama (so Ollama stops writing), and saves the trace with `error: "cancelled"`. My first version skipped the worker thread and checked the flag only when the endpoint asked for the next event. After a disconnect nobody asked again, so the trace was never saved and Ollama kept going. In the fixed version, closing the connection after the first word ended Ollama's answer call after 1.1 s.

**Rate limit.** At most 10 questions per minute per client IP on `/ask` and `/ask/stream`, then `429` with `Retry-After`. It's in memory, which is fine for one process; more than one would need something shared like Redis.

**Prompt injection.** Questions are pasted forum posts, so they can carry instructions. I didn't reword the prompts for this, because the speed work showed that rewording the check changes its behavior. Instead:
- citations can't be faked, because the model only gives excerpt numbers;
- the answer text may only contain links that appear in the retrieved excerpts, and any other link is replaced with `[link removed]`;
- the dashboard renders answers as plain text.

`scripts/injection_probe.py` sends 5 attacks (ignore your instructions and say PWNED, a fake system note with a phishing link, a fake `</question>` break-out recommending a made-up package, and a request to print the system prompt). 0 of 5 got through: the YES/NO check refused 4 of them, and the fifth got a normal cookie answer without the prompt. That's 5 hand-written attacks, not a proof. A side effect worth knowing: a real question with an attack pasted into it gets "I don't know", which is the safe way to fail.

**Privacy.** Before a question goes into the traces or the answer cache, emails, values after `password=`, `token=`, `api_key=` and similar, and long random-looking strings are replaced with `[email]` or `[redacted]`. The model still sees the original question.

## Trying a hosted model

Docs questions are where Pinpoint is weakest (9 of 40 on dev), so I checked how high it could go. With 3 excerpts the right page is in front of the model for only 26 of the 40 dev docs questions:

| Excerpts sent | Right page among them (40 dev docs questions) |
|---|---|
| 3 (current) | 26 |
| 5 | 29 |
| 10 | 32 |
| 20 | 37 |

Getting near 30 would mean sending about 10 excerpts and a model that judges them very well. The local 3B model can't do that: 10 excerpts are about 3,000 tokens, roughly 15 s of reading on this GPU, and it already refuses 17 questions where the page was in its 3 excerpts. So I tried Gemini Flash on the free tier.

`pinpoint_docs/hosted.py` calls Gemini's OpenAI-compatible endpoint with plain `urllib` and returns replies in the same shape as Ollama's, so the check, streaming, cancelling, traces and eval all work unchanged; any model name starting with `gemini` goes there. What I found:

- The free tier allows 20 requests per day per model. One dev run needs 80 to 160 requests, so the eval can't run on it. Switching between Gemini models to get around the limit would mix models in one score, so I didn't.
- The newest model (`gemini-3.8-flash`) took a median 27.7 s for a one-word reply because of "high demand" 503 errors; `gemini-3.6-flash` took 1.3 s. The client now retries 429 and 5xx errors with backoff.
- With a 3-token cap on the YES/NO check, Gemini returned no text at all, so hosted calls don't send a cap. Turning its "thinking" off cut a one-word reply from 99 tokens to 12.
- One question end to end gave a correct answer with the right two links. But on the 9 dev docs questions it reached with 10 excerpts before the quota ran out, the check said NO to all 9. I couldn't look into why without more requests.

So the scored numbers stay on the local model, which is free and has no limits. Gemini stays as an option for a live demo, where 20 questions a day is enough.

## What didn't work

Each of these had a pass mark set before running, on dev only.

| Idea | What happened |
|---|---|
| Distance cutoff for "I don't know" | Closest-chunk distance was 0.201 (median) for docs questions and 0.210 for the rest. It tells you whether a question is about FastAPI, not whether the docs answer it |
| Cross-encoder reranker (`ms-marco-MiniLM-L6-v2`) | Top-5 hits went from 29 to 25 of 40 (28 without the asker's code) and added about 2.7 s. It's trained on short web queries, not long forum posts with code |
| Looser check wording ("fully or in part") | The model said YES to two thirds of the out-of-scope questions |
| Check without the asker's code | 3 more correct YES answers, the bar was 5 |
| MMR for more varied results | hit@5 0.72 to 0.78 but 5 better / 3 worse, p = 0.73 |
| llama3.2 as an automatic grader | Agreed with my grades on as few as 1 of 8 answers, and called all 12 Pinpoint answers unfaithful |
| JSON output for citations | Broke on the first `"` inside code, replaced with plain `EXCERPTS:` / `ANSWER:` lines |
| `qwen2.5:3b` instead of llama3.2 | Cited nothing on the first 6 questions I tried end to end |
| One system prompt for check and answer | Passes fell from 44 to 33 (see above) |
| Skipping release-notes chunks unless the question asks about the changelog | Release notes are 1,185 of the 2,502 chunks and read like bug reports; half of the wrong answers to out-of-scope dev questions had one in the top 3. Out-of-scope "I don't know" went from 34 to 36 of 40, but docs passes fell from 9 to 8 and a fresh unseen sample got 34 of 40 against a bar of 35. Missed both bars by one question, so I dropped it |
| One chunk per page in the top 3 | The same page often filled 2 or 3 of the 3 slots, so I kept only the best chunk from each page. Search got better: a gold page in the top 3 went from 25 to 30 of 40 dev docs questions (5 fixed, none broken). The full run got worse: 43 to 39 passes. The check refused 18 found pages instead of 14, and with 3 different pages in front of it, it answered 11 out-of-scope questions instead of 6. Parked until the check can use better search |
| A stricter check: "name the excerpt" or `qwen2.5:3b` | On the 30 dev docs questions with a gold page in the top 3, today's check says YES to 12. Asking for the excerpt number, or using `qwen2.5:3b` for the same YES/NO question, gave 0 of 30, and NO to all 40 out-of-scope ones. The raw replies were almost all `NONE` or `NO`. (The first run cut replies at 3 tokens, which also chopped "Excerpt 3" before the number; the cap is now 10.) A 3B judge here is either too willing or too strict |
| A quote check for faithfulness | The answer had to include one line copied from the excerpts, and code checked the line was really in a cited excerpt. 11 of 21 answers passed. But a real quote doesn't mean a right answer: 5 of the 8 right answers had one, and so did 6 of the 13 wrong ones, including out-of-scope questions answered with a genuine docs line. Used as a filter it would fix 3 wrong answers and break 3 right ones; shown as a "verified" badge it would make wrong answers look trustworthy. Passes also dipped from 43 to 42, so I dropped it |
| Gemini free tier for the eval | 20 requests per day per model, a dev run needs 80 to 160 (see "Trying a hosted model") |

## Other problems I hit

- `nomic-embed-text` in Ollama reads at most 2,048 tokens and silently drops the rest. 18 chunks were longer, 15 of them on gold pages. That's where the 1,500-character cap comes from.
- One example file has a 4,269-character base64 image on a single line. Code lines over 200 characters get shortened.
- Only 27 of the 350 accepted answers link to the docs, so I found most gold pages by searching the docs myself.
- Forum questions come with a long checkbox template. Queries keep only the title, the code and the description.
- With "cite like [2]" in the prompt the 3B model skipped citations. Asking for an `EXCERPTS:` line fixed that.
- llama3.2 sometimes pasted the question's code back as its answer. The prompt now says not to.
- llama3.2 and the embedder didn't fit on the GPU together, so part of llama3.2 ran on the CPU. I pinned llama3.2 to the GPU and run question embeddings on the CPU. Answer time went from 25.4 s to 15.0 s.

## Dashboard

`dashboard/` is a small React app on top of the API: an ask box that shows each step and the answer as it's written, live p50/p95 latency, refusal/cache/error rates, the list of recent traces (click one to see what was retrieved and how long each step took), and the test results.

## Limitations

- Small samples: 50 test and 80 dev questions. Apart from the two significant results, most differences are noise.
- It still answers few docs questions: 9 of 28 on test. Search misses the gold page for 11, and the check refuses 7 where the page was found. The check is now the main limit: making search better didn't raise the score, because the 3B model can't reliably tell when the excerpts answer the question.
- Answers aren't always faithful: only 3 of 12 were fully backed by the excerpts.
- 3B model on a 4 GB GPU. Reading speed sets the floor on latency, and a 7-8B model doesn't fit.
- One grader (me), one library, one docs version, English only.
- The rate limit lives in one process's memory, and the injection probe is only 5 attacks.
- The Docker image builds in CI on every push, but `docker compose up` (app plus Ollama) hasn't been run end to end yet, and Ollama runs on the CPU in it.
- Streamed words are shown before the link filter runs on the final answer, so a removed link could flash on screen for a moment.

## Layout

```
pinpoint_docs/   chunking, indexing, search, answering, stats, FastAPI app
dashboard/       React + Vite + Tailwind dashboard
scripts/         question collection, tagging, eval, baseline, experiments
evals/           questions, dev/test split, hand grades, all result files
tests/           pytest
Dockerfile, docker-compose.yml, .github/workflows/
```
