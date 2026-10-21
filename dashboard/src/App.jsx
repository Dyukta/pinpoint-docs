import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  BookOpenCheck,
  ChevronRight,
  CircleCheck,
  CircleHelp,
  CircleSlash,
  Clock,
  Crosshair,
  Loader2,
  Search,
  ShieldCheck,
  Zap,
} from "lucide-react";

const POLL_MS = 5000;
const PAGE_SIZE = 20;
const IDK = "I don't know.";
const FAILURES = {
  search_missed_gold: "Search missed the right page",
  refused_with_gold: "Refused, though the right page was found",
  answered_unanswerable: "Answered a question the docs do not cover",
  cited_wrong_page: "Cited the wrong page",
  error: "Error",
};

function usePoll(url) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const response = await fetch(url);
        if (!response.ok) throw new Error(response.status >= 500 ? "offline" : `HTTP ${response.status}`);
        const body = await response.json();
        if (alive) {
          setData(body);
          setError(null);
        }
      } catch (e) {
        if (alive) setError(e.message === "Failed to fetch" ? "offline" : e.message);
      }
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [url]);
  return [data, error];
}

const pct = (x) => `${Math.round((x ?? 0) * 100)}%`;
const secs = (x) => `${(x ?? 0).toFixed(1)} s`;
const num = (x) => (x ?? 0).toLocaleString();
const section = (url) => url.replace("https://fastapi.tiangolo.com/", "").replace(/\/$/, "") || "home";
const firstLine = (text) => text.split("\n")[0];

function Card({ title, action, children, footer, scroll = false, className = "" }) {
  return (
    <section className={`rounded-2xl border border-slate-200 bg-white p-6 shadow-sm ${scroll ? "flex min-h-0 flex-col" : ""} ${className}`}>
      {(title || action) && (
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          </div>
          {action}
        </div>
      )}
      {scroll ? <div className="min-h-0 flex-1 scroll-theme overflow-y-auto pr-4">{children}</div> : children}
      {footer}
    </section>
  );
}

const TONES = {
  violet: "bg-violet-100 text-violet-600",
  amber: "bg-amber-100 text-amber-600",
  rose: "bg-rose-100 text-rose-600",
  emerald: "bg-emerald-100 text-emerald-600",
  sky: "bg-sky-100 text-sky-600",
};

function Stat({ label, value, hint, icon: Icon, tone }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <span className="text-sm text-slate-500">{label}</span>
        <span className={`rounded-xl p-2 ${TONES[tone]}`}>
          <Icon size={18} />
        </span>
      </div>
      <div className="mt-2 text-3xl font-semibold text-slate-900">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

function Meter({ value, max, tone = "from-violet-500 to-indigo-500" }) {
  const width = max ? Math.max(3, (value / max) * 100) : 0;
  return (
    <div className="h-2 rounded-full bg-slate-100">
      <div className={`h-2 rounded-full bg-gradient-to-r ${tone}`} style={{ width: `${width}%` }} />
    </div>
  );
}

function Verdict({ trace }) {
  const [text, style] = trace.error
    ? ["Error", "bg-rose-100 text-rose-700"]
    : trace.cached
      ? ["Cached", "bg-sky-100 text-sky-700"]
      : trace.answer === IDK
        ? ["I don't know", "bg-amber-100 text-amber-700"]
        : ["Answered", "bg-violet-100 text-violet-700"];
  return <span className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>{text}</span>;
}

function Steps({ trace, dark = false }) {
  const muted = dark ? "text-indigo-200" : "text-slate-500";
  const strong = dark ? "text-white" : "text-slate-800";
  if (trace.cached) {
    return <p className={`text-sm ${muted}`}>Served from the answer cache: an almost identical question was answered before with the same settings.</p>;
  }
  const steps = [
    ["Retrieve", "BM25 + vector search, fused with RRF", trace.search_seconds],
    ["Check", trace.answerable ? "Excerpts answer it: YES" : "Excerpts answer it: NO", trace.check_seconds],
    ["Answer", trace.answer_seconds == null ? "Skipped" : "Grounded answer with links", trace.answer_seconds],
  ];
  const max = Math.max(...steps.map(([, , s]) => s ?? 0), 0.1);
  return (
    <ol className="space-y-3">
      {steps.map(([name, detail, s], i) => (
        <li key={name} className="grid grid-cols-[1.75rem_1fr_3.5rem] items-center gap-3 text-sm">
          <span className={`grid h-7 w-7 place-items-center rounded-full text-xs font-semibold ${dark ? "bg-white/20 text-white" : "bg-violet-100 text-violet-700"}`}>{i + 1}</span>
          <div>
            <div className="mb-1 flex justify-between gap-2">
              <span className={`font-medium ${strong}`}>{name}</span>
              <span className={`text-xs ${muted}`}>{detail}</span>
            </div>
            <div className={`h-2 rounded-full ${dark ? "bg-white/15" : "bg-slate-100"}`}>
              <div
                className={`h-2 rounded-full ${s == null ? "bg-transparent" : dark ? "bg-white/80" : "bg-gradient-to-r from-violet-500 to-indigo-500"}`}
                style={{ width: `${s == null ? 0 : Math.max(3, (s / max) * 100)}%` }}
              />
            </div>
          </div>
          <span className={`text-right font-mono text-xs ${muted}`}>{secs(s)}</span>
        </li>
      ))}
    </ol>
  );
}

function AskBox() {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [trace, setTrace] = useState(null);
  const controller = useRef(null);

  const ask = async (e) => {
    e.preventDefault();
    if (question.trim().length < 3 || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    setTrace(null);
    controller.current = new AbortController();
    const { signal } = controller.current;
    try {
      const response = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal,
      });
      if (!response.ok) throw new Error(response.status >= 500 ? "the API is not running" : `HTTP ${response.status}`);
      const body = await response.json();
      setResult(body);
      const detail = await fetch(`/traces/${body.trace_id}`, { signal });
      if (detail.ok) setTrace(await detail.json());
    } catch (err) {
      if (err.name !== "AbortError") setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const abstained = result?.answer === IDK;

  return (
    <section className="rounded-2xl bg-gradient-to-br from-violet-600 via-indigo-600 to-indigo-800 p-6 text-white shadow-lg">
      <h2 className="text-lg font-semibold">Search the docs</h2>
      <form onSubmit={ask} className="mt-4 flex gap-3">
        <div className="relative flex-1">
          <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-indigo-200" />
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="How do I declare a request body?"
            className="w-full rounded-xl border border-white/20 bg-white/10 py-3 pl-11 pr-4 text-white placeholder:text-indigo-200 focus:border-white/60 focus:outline-none"
          />
        </div>
        {busy ? (
          <button
            key="cancel"
            type="button"
            onClick={() => controller.current.abort()}
            className="flex items-center gap-2 rounded-xl border border-white/40 px-7 py-3 font-semibold text-white hover:bg-white/10"
          >
            <Loader2 size={18} className="animate-spin" />
            Cancel
          </button>
        ) : (
          <button key="search" className="rounded-xl bg-white px-7 py-3 font-semibold text-violet-700 shadow-sm hover:bg-indigo-50">
            Search
          </button>
        )}
      </form>
      {busy && <p className="mt-4 text-sm text-indigo-100">Searching the docs, checking the excerpts, then answering. About 20 seconds on a local 3B model.</p>}
      {error && <p className="mt-4 text-sm text-rose-200">Request failed: {error}.</p>}
      {result && (
        <div className="mt-5 grid gap-4 lg:grid-cols-5">
          <div className={`rounded-xl bg-white/10 p-4 lg:col-span-3 ${abstained ? "flex items-center" : ""}`}>
            {abstained ? (
              <div className="flex gap-3">
                <CircleSlash size={20} className="mt-0.5 shrink-0 text-amber-200" />
                <div>
                  <div className="font-semibold">I don't know.</div>
                  <div className="mt-1 text-sm text-indigo-100">The retrieved sections do not answer this, so Pinpoint does not guess.</div>
                </div>
              </div>
            ) : (
              <>
                <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{result.answer}</pre>
                <div className="mt-4 text-xs font-semibold uppercase tracking-wider text-indigo-200">Grounded in</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {result.sources.map((url) => (
                    <a key={url} href={url} target="_blank" rel="noreferrer" className="rounded-full bg-white/15 px-3 py-1 text-xs hover:bg-white/25">
                      {section(url)}
                    </a>
                  ))}
                </div>
              </>
            )}
          </div>
          <div className="rounded-xl bg-white/10 p-4 lg:col-span-2">
            <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-indigo-200">How it was answered</div>
            {trace ? <Steps trace={trace} dark /> : <Loader2 size={18} className="animate-spin text-indigo-200" />}
          </div>
        </div>
      )}
    </section>
  );
}

function TraceTable({ traces, onPick, picked }) {
  if (!traces?.length) return <p className="py-10 text-center text-sm text-slate-500">No questions yet. Search above.</p>;
  return (
    <table className="w-full table-fixed text-left text-sm">
      <thead className="sticky top-0 bg-white text-xs uppercase text-slate-500">
        <tr>
          <th className="pb-2 font-medium">Question</th>
          <th className="w-28 pb-2 font-medium">Result</th>
          <th className="w-16 pb-2 text-right font-medium">Time</th>
        </tr>
      </thead>
      <tbody>
        {traces.map((t) => (
          <tr
            key={t.trace_id}
            onClick={() => onPick(t.trace_id)}
            className={`cursor-pointer border-t border-slate-100 hover:bg-violet-50 ${picked === t.trace_id ? "bg-violet-50" : ""}`}
          >
            <td className="truncate py-2.5 pr-4 text-slate-800">{firstLine(t.question)}</td>
            <td className="py-2.5">
              <Verdict trace={t} />
            </td>
            <td className="py-2.5 text-right text-slate-600 tabular-nums">{secs(t.seconds)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Pipeline({ stats }) {
  const steps = stats?.steps_p50 ?? {};
  const stages = [
    ["Retrieve", "BM25 + vector, RRF", steps.search],
    ["Check", "Do the excerpts answer it?", steps.check],
    ["Answer", "Grounded, with links", steps.answer],
  ];
  const max = Math.max(...stages.map(([, , s]) => s ?? 0), 0.1);
  return (
    <div>
      <div className="flex items-stretch gap-2">
        {stages.map(([name, detail, s], i) => (
          <div key={name} className="flex flex-1 items-center gap-2">
            <div className="flex-1 rounded-xl bg-slate-50 p-4">
              <div className="font-medium text-slate-800">{name}</div>
              <div className="text-xs text-slate-500">{detail}</div>
              <div className="mb-2 mt-2 text-2xl font-semibold text-slate-900">{secs(s)}</div>
              <Meter value={s ?? 0} max={max} />
            </div>
            {i < stages.length - 1 && <ChevronRight size={18} className="shrink-0 text-slate-300" />}
          </div>
        ))}
      </div>
      <p className="mt-4 text-xs text-slate-500">
        Median seconds per stage. Questions the check refuses skip the answer stage. Tokens per 1,000 questions: {num(stats?.tokens_per_1000.prompt)} in, {num(stats?.tokens_per_1000.output)} out.
      </p>
    </div>
  );
}

function SearchPage({ go }) {
  const [stats] = usePoll("/stats?last=200");
  const [latest] = usePoll("/traces?limit=6");
  const answered = stats ? 1 - (stats.refusal_rate ?? 0) - (stats.error_rate ?? 0) : null;

  return (
    <div className="space-y-6">
      <AskBox />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Answered with sources" value={pct(answered)} hint={`${num(stats?.requests)} questions traced`} icon={CircleCheck} tone="emerald" />
        <Stat label="Said I don't know" value={pct(stats?.refusal_rate)} hint="no grounded answer found" icon={CircleHelp} tone="amber" />
        <Stat label="Latency p50" value={secs(stats?.latency.p50)} hint={`p95 ${secs(stats?.latency.p95)}`} icon={Clock} tone="violet" />
        <Stat label="Cache hits" value={pct(stats?.cache_hit_rate)} hint={`errors ${pct(stats?.error_rate)}`} icon={Zap} tone="sky" />
      </div>
      <div className="grid gap-6 xl:grid-cols-5">
        <Card title="Pipeline" className="xl:col-span-3">
          <Pipeline stats={stats} />
        </Card>
        <Card
          title="Latest questions"
          className="xl:col-span-2"
          action={
            <button onClick={() => go("traces")} className="flex items-center gap-1 text-sm font-medium text-violet-600 hover:text-violet-700">
              All traces <ArrowRight size={14} />
            </button>
          }
        >
          <TraceTable traces={latest?.items} onPick={() => go("traces")} />
        </Card>
      </div>
    </div>
  );
}

function Chunks({ trace }) {
  const scores = trace.scores ?? [];
  const max = Math.max(...scores, 0.0001);
  if (!trace.retrieved?.length) return <p className="text-sm text-slate-500">Nothing retrieved.</p>;
  return (
    <ul className="space-y-3">
      {trace.retrieved.map((chunk, i) => (
        <li key={chunk} className="text-xs">
          <div className="mb-1 flex justify-between gap-3">
            <span className="truncate font-mono text-slate-700">{chunk}</span>
            <span className="font-mono text-slate-500">{scores[i]?.toFixed(4)}</span>
          </div>
          <Meter value={scores[i] ?? 0} max={max} />
        </li>
      ))}
    </ul>
  );
}

function Inspector({ id }) {
  const [trace, setTrace] = useState(null);
  useEffect(() => {
    setTrace(null);
    fetch(`/traces/${id}`).then((r) => r.json()).then(setTrace);
  }, [id]);
  if (!trace) return <Loader2 className="mx-auto animate-spin text-violet-500" />;
  return (
    <div className="space-y-5 text-sm">
      <div className="flex items-center justify-between">
        <Verdict trace={trace} />
        <span className="font-mono text-xs text-slate-400">{trace.trace_id}</span>
      </div>
      <div>
        <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-500">Question</div>
        <p className="whitespace-pre-wrap text-slate-700">{trace.question}</p>
      </div>
      <div>
        <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-500">Answer</div>
        <pre className="whitespace-pre-wrap font-sans text-slate-800">{trace.answer}</pre>
        {trace.error && <p className="mt-1 font-mono text-xs text-rose-600">{trace.error}</p>}
      </div>
      <div>
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Steps</div>
        <Steps trace={trace} />
      </div>
      <div>
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Retrieved chunks, RRF score</div>
        <Chunks trace={trace} />
      </div>
      <p className="text-xs text-slate-500">
        {num(trace.prompt_tokens)} prompt tokens · {num(trace.output_tokens)} output tokens
      </p>
    </div>
  );
}

function Pager({ page, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const first = total ? page * PAGE_SIZE + 1 : 0;
  const last = Math.min(total, (page + 1) * PAGE_SIZE);
  const button = "rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-violet-700 hover:bg-violet-50 disabled:cursor-not-allowed disabled:text-slate-300 disabled:hover:bg-transparent";
  return (
    <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4 text-sm text-slate-500">
      <span>
        {first}–{last} of {total}
      </span>
      <div className="flex items-center gap-2">
        <button className={button} disabled={page === 0} onClick={() => onPage(page - 1)}>
          Previous
        </button>
        <span className="px-2">
          Page {page + 1} of {pages}
        </span>
        <button className={button} disabled={page >= pages - 1} onClick={() => onPage(page + 1)}>
          Next
        </button>
      </div>
    </div>
  );
}

function Traces() {
  const [page, setPage] = useState(0);
  const [data] = usePoll(`/traces?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`);
  const [picked, setPicked] = useState(null);
  return (
    <div className="grid gap-6 xl:h-[calc(100vh-10rem)] xl:grid-cols-5">
      <Card
        title="All questions"
       
        scroll
        className="xl:col-span-3 xl:h-full"
        footer={<Pager page={page} total={data?.total ?? 0} onPage={setPage} />}
      >
        <TraceTable traces={data?.items} onPick={setPicked} picked={picked} />
      </Card>
      <Card title="Inspector" scroll className="xl:col-span-2 xl:h-full">
        {picked ? <Inspector id={picked} /> : <p className="py-10 text-center text-sm text-slate-500">Pick a question to see how it was answered.</p>}
      </Card>
    </div>
  );
}

function Compare({ run, base }) {
  const docs = (r) => r.by_tag.docs ?? { passed: 0, total: 0 };
  const other = (r) =>
    Object.entries(r.by_tag)
      .filter(([tag]) => tag !== "docs")
      .reduce((a, [, v]) => ({ passed: a.passed + v.passed, total: a.total + v.total }), { passed: 0, total: 0 });
  const rows = [
    ["Passed", (r) => `${r.passed} / ${r.questions}`],
    ["Docs questions: cited the right page", (r) => `${docs(r).passed} / ${docs(r).total}`],
    ["Other questions: said I don't know", (r) => `${other(r).passed} / ${other(r).total}`],
    ["Said I don't know overall", (r) => pct(r.refusal_rate)],
    ["Latency p50 / p95", (r) => `${secs(r.latency.p50)} / ${secs(r.latency.p95)}`],
  ];
  return (
    <table className="w-full text-sm">
      <thead className="text-xs uppercase text-slate-500">
        <tr>
          <th className="pb-2 text-left font-medium" />
          <th className="pb-2 text-right font-medium">Without check</th>
          <th className="pb-2 text-right font-medium text-violet-600">With check</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([label, value]) => (
          <tr key={label} className="border-t border-slate-100">
            <td className="py-2.5 text-slate-700">{label}</td>
            <td className="py-2.5 text-right text-slate-500 tabular-nums">{value(base)}</td>
            <td className="py-2.5 text-right font-semibold text-slate-900 tabular-nums">{value(run)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Evaluation() {
  const [run, error] = usePoll("/eval");
  if (error) return <Card title="Evaluation"><p className="text-sm text-slate-500">No test run found ({error}).</p></Card>;
  if (!run) return <Loader2 className="mx-auto animate-spin text-violet-500" />;
  const base = run.without_check;
  const failures = Object.entries(run.failures);
  const most = Math.max(...failures.map(([, n]) => n), 1);

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-center gap-3 rounded-xl bg-gradient-to-br from-violet-600 via-indigo-600 to-indigo-800 px-5 py-3 text-white shadow-lg">
        <span className="rounded-lg bg-white/15 p-2">
          <ShieldCheck size={20} />
        </span>
        <div className="flex-1">
          <div className="text-base font-semibold">
            {run.passed} of {run.questions} held-out questions passed with the abstention check{base && <span className="text-indigo-200">, {base.passed} without it</span>}
          </div>
        </div>
      </section>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Passed" value={`${run.passed} / ${run.questions}`} hint="held-out test" icon={BookOpenCheck} tone="violet" />
        <Stat label="Docs questions" value={`${run.by_tag.docs?.passed ?? 0} / ${run.by_tag.docs?.total ?? 0}`} hint="cited the right page" icon={Crosshair} tone="emerald" />
        <Stat label="Said I don't know" value={pct(run.refusal_rate)} hint="of all test questions" icon={CircleHelp} tone="amber" />
        <Stat label="Latency p95" value={secs(run.latency.p95)} hint={`p50 ${secs(run.latency.p50)}`} icon={Clock} tone="sky" />
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        {base && (
          <Card title="With and without the check">
            <Compare run={run} base={base} />
          </Card>
        )}
        <Card title="What still fails">
          <div className="space-y-4">
            {failures.map(([kind, n]) => (
              <div key={kind}>
                <div className="mb-1 flex justify-between text-sm">
                  <span className="text-slate-700">{FAILURES[kind] ?? kind}</span>
                  <span className="text-slate-500">{n}</span>
                </div>
                <Meter value={n} max={most} tone="from-rose-400 to-rose-500" />
              </div>
            ))}
          </div>
        </Card>
        <Card title="By question type" className="xl:col-span-2">
          <div className="space-y-4">
            {Object.entries(run.by_tag).map(([tag, v]) => (
              <div key={tag}>
                <div className="mb-1 flex justify-between text-sm">
                  <span className="text-slate-700">{tag}</span>
                  <span className="text-slate-500">
                    {v.passed} / {v.total} passed
                  </span>
                </div>
                <Meter value={v.passed} max={v.total} />
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

const PAGES = {
  search: { label: "Search", title: "Search", view: SearchPage },
  traces: { label: "Traces", title: "Traces", view: Traces },
  evaluation: { label: "Evaluation", title: "Evaluation", view: Evaluation },
};

function ApiStatus() {
  const [, error] = usePoll("/stats?last=1");
  const online = !error;
  return (
    <div className="flex items-center gap-2 rounded-xl bg-white/5 p-3 text-sm font-medium text-white">
      <span className={`h-2 w-2 rounded-full ${online ? "bg-emerald-400" : "bg-rose-400"}`} />
      {online ? "API connected" : "API not connected"}
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState("search");
  const { title, view: View } = PAGES[page];

  return (
    <div className="flex min-h-screen bg-[#f4f3fb] font-sans text-slate-800">
      <aside className="sticky top-0 flex h-screen w-64 shrink-0 flex-col bg-gradient-to-b from-[#221a5c] to-[#15103d] p-4 text-indigo-100">
        <div className="mb-6 px-3 py-1 text-xl font-semibold text-white">Pinpoint</div>
        <nav className="flex-1">
          {Object.entries(PAGES).map(([key, { label }]) => (
            <button
              key={key}
              onClick={() => setPage(key)}
              className={`mb-1 flex w-full items-center rounded-xl px-3 py-2.5 text-left font-medium ${key === page ? "bg-violet-600 text-white shadow" : "hover:bg-white/5"}`}
            >
              {label}
            </button>
          ))}
        </nav>
        <ApiStatus />
      </aside>
      <main className="flex-1 overflow-x-hidden px-6 py-8 lg:px-10">
        <header className="mb-6">
          <h1 className="text-3xl font-semibold text-slate-900">{title}</h1>
        </header>
        <View go={setPage} />
      </main>
    </div>
  );
}
