import { useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  BookOpenCheck,
  CircleHelp,
  Clock,
  Crosshair,
  LayoutGrid,
  ListTree,
  Loader2,
  Moon,
  Send,
  Sun,
  Zap,
} from "lucide-react";

const POLL_MS = 5000;
const FAILURES = {
  search_missed_gold: "Search missed the gold page",
  refused_with_gold: "Refused although the page was found",
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
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const body = await response.json();
        if (alive) {
          setData(body);
          setError(null);
        }
      } catch (e) {
        if (alive) setError(e.message);
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

const pct = (x) => (x == null ? "–" : `${Math.round(x * 100)}%`);
const secs = (x) => (x == null ? "–" : `${x.toFixed(1)} s`);
const num = (x) => (x == null ? "–" : x.toLocaleString());

function greeting() {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

function Card({ title, action, children, className = "" }) {
  return (
    <section className={`rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-[#1a1640] ${className}`}>
      {(title || action) && (
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

function Stat({ label, value, hint, icon: Icon, tone }) {
  const tones = {
    violet: "bg-violet-100 text-violet-600 dark:bg-violet-500/15 dark:text-violet-300",
    amber: "bg-amber-100 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300",
    rose: "bg-rose-100 text-rose-600 dark:bg-rose-500/15 dark:text-rose-300",
    emerald: "bg-emerald-100 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300",
  };
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-[#1a1640]">
      <div className="flex items-start justify-between">
        <span className="text-sm text-slate-500 dark:text-slate-400">{label}</span>
        <span className={`rounded-xl p-2 ${tones[tone]}`}>
          <Icon size={18} />
        </span>
      </div>
      <div className="mt-2 text-3xl font-semibold">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</div>}
    </div>
  );
}

function Bar({ label, value, max, detail }) {
  const width = max ? Math.max(4, (value / max) * 100) : 0;
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm">
        <span>{label}</span>
        <span className="text-slate-500 dark:text-slate-400">{detail}</span>
      </div>
      <div className="h-2.5 rounded-full bg-slate-100 dark:bg-white/10">
        <div className="h-2.5 rounded-full bg-gradient-to-r from-violet-500 to-indigo-500" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function Outcome({ trace }) {
  const [text, style] = trace.error
    ? ["Error", "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300"]
    : trace.cached
      ? ["Cached", "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"]
      : trace.answer === "I don't know."
        ? ["I don't know", "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300"]
        : ["Answered", "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300"];
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>{text}</span>;
}

function TraceTable({ traces, onPick, picked }) {
  if (!traces?.length) return <p className="py-8 text-center text-slate-500">No requests yet. Ask something above.</p>;
  return (
    <table className="w-full text-left text-sm">
      <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
        <tr>
          <th className="pb-2 font-medium">Question</th>
          <th className="pb-2 font-medium">Outcome</th>
          <th className="pb-2 text-right font-medium">Time</th>
        </tr>
      </thead>
      <tbody>
        {traces.map((t) => (
          <tr
            key={t.trace_id}
            onClick={() => onPick?.(t.trace_id)}
            className={`cursor-pointer border-t border-slate-100 hover:bg-violet-50 dark:border-white/5 dark:hover:bg-white/5 ${picked === t.trace_id ? "bg-violet-50 dark:bg-white/5" : ""}`}
          >
            <td className="max-w-md truncate py-2.5 pr-4">{t.question}</td>
            <td className="py-2.5">
              <Outcome trace={t} />
            </td>
            <td className="py-2.5 text-right tabular-nums">{secs(t.seconds)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function AskBox() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const ask = async (e) => {
    e.preventDefault();
    if (question.trim().length < 3 || busy) return;
    setBusy(true);
    setError(null);
    const start = performance.now();
    try {
      const response = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setResult({ ...(await response.json()), seconds: (performance.now() - start) / 1000 });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-2xl bg-gradient-to-br from-violet-600 via-indigo-600 to-indigo-800 p-6 text-white shadow-lg">
      <h2 className="text-lg font-semibold">Ask the docs</h2>
      <p className="mt-1 text-sm text-indigo-100">Answers come only from the FastAPI 0.150.0 docs, with links, or "I don't know".</p>
      <form onSubmit={ask} className="mt-4 flex gap-3">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="How do I declare a request body?"
          className="flex-1 rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-white placeholder:text-indigo-200 focus:border-white/60 focus:outline-none"
        />
        <button
          disabled={busy}
          className="flex items-center gap-2 rounded-xl bg-white/20 px-5 py-3 font-medium hover:bg-white/30 disabled:opacity-60"
        >
          {busy ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
          {busy ? "Searching" : "Ask"}
        </button>
      </form>
      {error && <p className="mt-4 text-sm text-rose-200">Request failed: {error}. Is the API running?</p>}
      {result && (
        <div className="mt-5 rounded-xl bg-white/10 p-4">
          <div className="mb-2 flex gap-2 text-xs">
            {result.cached && <span className="rounded-full bg-emerald-400/25 px-2.5 py-0.5">From cache</span>}
            <span className="rounded-full bg-white/15 px-2.5 py-0.5">{secs(result.seconds)}</span>
          </div>
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{result.answer}</pre>
          {result.sources.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm">
              {result.sources.map((url) => (
                <li key={url}>
                  <a href={url} target="_blank" rel="noreferrer" className="underline decoration-white/40 hover:decoration-white">
                    {url.replace("https://fastapi.tiangolo.com/", "")}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function Overview({ go }) {
  const [stats, statsError] = usePoll("/stats?last=200");
  const [traces] = usePoll("/traces?limit=8");
  const steps = stats?.steps_p50 ?? {};
  const max = Math.max(...Object.values(steps).map((v) => v ?? 0), 0);

  return (
    <div className="space-y-6">
      <AskBox />
      {statsError && <p className="text-sm text-rose-600">Cannot reach the API ({statsError}). Start it with fastapi dev pinpoint_docs/api.py</p>}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Requests" value={num(stats?.requests)} hint="last 200 traced" icon={Activity} tone="violet" />
        <Stat label="Latency p50" value={secs(stats?.latency.p50)} hint={`p95 ${secs(stats?.latency.p95)}`} icon={Clock} tone="amber" />
        <Stat label="Said I don't know" value={pct(stats?.refusal_rate)} hint={`errors ${pct(stats?.error_rate)}`} icon={CircleHelp} tone="rose" />
        <Stat label="Cache hits" value={pct(stats?.cache_hit_rate)} hint="same question, same settings" icon={Zap} tone="emerald" />
      </div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card title="Where the time goes" className="xl:col-span-1">
          <div className="space-y-4">
            {Object.entries(steps).map(([step, value]) => (
              <Bar key={step} label={step} value={value ?? 0} max={max} detail={`p50 ${secs(value)}`} />
            ))}
          </div>
          <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
            Tokens per 1,000 questions: {num(stats?.tokens_per_1000.prompt)} in, {num(stats?.tokens_per_1000.output)} out
          </p>
        </Card>
        <Card
          title="Recent requests"
          className="xl:col-span-2"
          action={
            <button onClick={() => go("requests")} className="flex items-center gap-1 text-sm font-medium text-violet-600 dark:text-violet-300">
              All requests <ArrowRight size={14} />
            </button>
          }
        >
          <TraceTable traces={traces} onPick={() => go("requests")} />
        </Card>
      </div>
    </div>
  );
}

function TraceDetail({ id }) {
  const [trace, setTrace] = useState(null);
  useEffect(() => {
    setTrace(null);
    fetch(`/traces/${id}`).then((r) => r.json()).then(setTrace);
  }, [id]);
  if (!trace) return <Loader2 className="mx-auto animate-spin text-violet-500" />;
  return (
    <div className="space-y-4 text-sm">
      <div>
        <div className="mb-1 text-xs uppercase text-slate-500">Question</div>
        <p className="max-h-32 overflow-auto whitespace-pre-wrap">{trace.question}</p>
      </div>
      <div>
        <div className="mb-1 text-xs uppercase text-slate-500">Answer</div>
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap font-sans">{trace.answer}</pre>
        {trace.error && <p className="mt-1 text-rose-600">{trace.error}</p>}
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        {["search", "check", "answer"].map((step) => (
          <div key={step} className="rounded-xl bg-slate-50 p-2 dark:bg-white/5">
            <div className="text-xs text-slate-500">{step}</div>
            <div className="font-semibold tabular-nums">{secs(trace[`${step}_seconds`])}</div>
          </div>
        ))}
      </div>
      <div>
        <div className="mb-1 text-xs uppercase text-slate-500">Retrieved chunks (RRF score)</div>
        <ul className="space-y-1">
          {(trace.retrieved ?? []).map((chunk, i) => (
            <li key={chunk} className="flex justify-between gap-2">
              <span className="truncate">{chunk}</span>
              <span className="tabular-nums text-slate-500">{trace.scores?.[i]?.toFixed(4)}</span>
            </li>
          ))}
        </ul>
      </div>
      <p className="text-xs text-slate-500">
        {num(trace.prompt_tokens)} prompt tokens · {num(trace.output_tokens)} output tokens · trace {trace.trace_id}
      </p>
    </div>
  );
}

function Requests() {
  const [traces] = usePoll("/traces?limit=100");
  const [picked, setPicked] = useState(null);
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
      <Card title="Requests" className="xl:col-span-3">
        <TraceTable traces={traces} onPick={setPicked} picked={picked} />
      </Card>
      <Card title="Trace" className="xl:col-span-2">
        {picked ? <TraceDetail id={picked} /> : <p className="py-8 text-center text-slate-500">Pick a request to see what was retrieved and how long each step took.</p>}
      </Card>
    </div>
  );
}

function Evaluation() {
  const [run, error] = usePoll("/eval");
  if (error) return <Card title="Evaluation"><p className="text-slate-500">No test run found ({error}).</p></Card>;
  if (!run) return <Loader2 className="mx-auto animate-spin text-violet-500" />;
  const failures = Object.entries(run.failures);
  const most = Math.max(...failures.map(([, n]) => n), 1);
  const docs = run.by_tag.docs ?? { passed: 0, total: 0 };
  const other = Object.entries(run.by_tag).filter(([tag]) => tag !== "docs").reduce((a, [, v]) => ({ passed: a.passed + v.passed, total: a.total + v.total }), { passed: 0, total: 0 });

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Passed" value={`${run.passed} / ${run.questions}`} hint="held-out test questions" icon={BookOpenCheck} tone="violet" />
        <Stat label="Docs questions" value={`${docs.passed} / ${docs.total}`} hint="cited a gold page" icon={Crosshair} tone="emerald" />
        <Stat label="Other questions" value={`${other.passed} / ${other.total}`} hint={'said "I don\'t know"'} icon={CircleHelp} tone="rose" />
        <Stat label="Latency p95" value={secs(run.latency.p95)} hint={`p50 ${secs(run.latency.p50)}`} icon={Clock} tone="amber" />
      </div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card title="Failures">
          <div className="space-y-4">
            {failures.map(([kind, n]) => (
              <Bar key={kind} label={FAILURES[kind] ?? kind} value={n} max={most} detail={n} />
            ))}
          </div>
        </Card>
        <Card title="By question type">
          <div className="space-y-4">
            {Object.entries(run.by_tag).map(([tag, v]) => (
              <Bar key={tag} label={tag} value={v.passed} max={v.total} detail={`${v.passed} / ${v.total} passed`} />
            ))}
          </div>
          <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">From {run.run}. Passing means the answer cited a gold page, or said "I don't know" when the docs do not cover the question.</p>
        </Card>
      </div>
    </div>
  );
}

const PAGES = {
  overview: { label: "Overview", icon: LayoutGrid, title: greeting, subtitle: "Live from data/traces.jsonl, refreshed every 5 seconds", view: Overview },
  requests: { label: "Requests", icon: ListTree, title: () => "Requests", subtitle: "Every traced question, newest first", view: Requests },
  evaluation: { label: "Evaluation", icon: BookOpenCheck, title: () => "Evaluation", subtitle: "Held-out test questions, reviewed by hand", view: Evaluation },
};
const SECTIONS = [
  ["Monitoring", ["overview", "requests"]],
  ["Quality", ["evaluation"]],
];

function readTheme() {
  try {
    return localStorage.getItem("theme") === "dark";
  } catch {
    return false;
  }
}

export default function App() {
  const [page, setPage] = useState("overview");
  const [dark, setDark] = useState(readTheme);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch {
      return;
    }
  }, [dark]);

  const { title, subtitle, view: View } = PAGES[page];

  return (
    <div className="flex min-h-screen bg-[#f4f3fb] font-sans text-slate-800 dark:bg-[#0f0c29] dark:text-slate-100">
      <aside className="sticky top-0 flex h-screen w-64 shrink-0 flex-col bg-gradient-to-b from-[#221a5c] to-[#15103d] p-4 text-indigo-100">
        <div className="mb-6 flex items-center gap-3 px-2 py-1">
          <span className="rounded-xl bg-violet-500 p-2 text-white">
            <Crosshair size={18} />
          </span>
          <span className="text-lg font-semibold text-white">Pinpoint</span>
        </div>
        <nav className="flex-1 space-y-6">
          {SECTIONS.map(([section, keys]) => (
            <div key={section}>
              <div className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-indigo-300/70">{section}</div>
              {keys.map((key) => {
                const { label, icon: Icon } = PAGES[key];
                const active = key === page;
                return (
                  <button
                    key={key}
                    onClick={() => setPage(key)}
                    className={`mb-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left font-medium ${active ? "bg-violet-600 text-white shadow" : "hover:bg-white/5"}`}
                  >
                    <Icon size={18} />
                    {label}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="mb-3 grid grid-cols-2 rounded-xl bg-white/5 p-1 text-sm">
          <button onClick={() => setDark(false)} className={`flex items-center justify-center gap-1.5 rounded-lg py-1.5 ${dark ? "" : "bg-violet-600 text-white"}`}>
            <Sun size={14} /> Light
          </button>
          <button onClick={() => setDark(true)} className={`flex items-center justify-center gap-1.5 rounded-lg py-1.5 ${dark ? "bg-violet-600 text-white" : ""}`}>
            <Moon size={14} /> Dark
          </button>
        </div>
        <div className="flex items-center gap-3 rounded-xl bg-white/5 p-3">
          <span className="grid h-9 w-9 place-items-center rounded-full bg-violet-500 text-sm font-semibold text-white">L3</span>
          <div className="text-sm">
            <div className="font-medium text-white">llama3.2 · local</div>
            <div className="text-xs text-indigo-300">FastAPI docs 0.150.0</div>
          </div>
        </div>
      </aside>
      <main className="flex-1 overflow-x-hidden px-6 py-8 lg:px-10">
        <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold">{title()}</h1>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>
          </div>
          <span className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium uppercase tracking-wide text-slate-600 dark:border-white/10 dark:bg-[#1a1640] dark:text-slate-300">
            <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" /> Live
          </span>
        </header>
        <View go={setPage} />
      </main>
    </div>
  );
}
