import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { usePoll } from "../api";
import TraceTable from "../components/TraceTable";
import { Card, Meter, Steps, Verdict } from "../components/ui";
import { num } from "../format";

const PAGE_SIZE = 20;

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

function Label({ children }) {
  return <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-500">{children}</div>;
}

function Inspector({ id }) {
  const [trace, setTrace] = useState(null);
  useEffect(() => {
    setTrace(null);
    fetch(`/traces/${id}`)
      .then((r) => r.json())
      .then(setTrace);
  }, [id]);
  if (!trace) return <Loader2 className="mx-auto animate-spin text-violet-500" />;
  return (
    <div className="space-y-5 text-sm">
      <div className="flex items-center justify-between">
        <Verdict trace={trace} />
        <span className="font-mono text-xs text-slate-400">{trace.trace_id}</span>
      </div>
      <div>
        <Label>Question</Label>
        <p className="whitespace-pre-wrap break-words text-slate-700">{trace.question}</p>
      </div>
      <div>
        <Label>Answer</Label>
        <pre className="whitespace-pre-wrap break-words font-sans text-slate-800">{trace.answer}</pre>
        {trace.error && <p className="mt-1 font-mono text-xs text-rose-600">{trace.error}</p>}
      </div>
      <div>
        <Label>Steps</Label>
        <Steps trace={trace} />
      </div>
      <div>
        <Label>Retrieved chunks, RRF score</Label>
        <Chunks trace={trace} />
      </div>
      <p className="text-xs text-slate-500">
        {num(trace.prompt_tokens)} prompt tokens, {num(trace.output_tokens)} output tokens
      </p>
    </div>
  );
}

function Pager({ page, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const first = total ? page * PAGE_SIZE + 1 : 0;
  const last = Math.min(total, (page + 1) * PAGE_SIZE);
  const button =
    "rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-violet-700 hover:bg-violet-50 disabled:cursor-not-allowed disabled:text-slate-300 disabled:hover:bg-transparent";
  return (
    <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4 text-sm text-slate-500">
      <span>
        {first}-{last} of {total}
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

export default function Traces() {
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
        {picked ? (
          <Inspector id={picked} />
        ) : (
          <p className="py-10 text-center text-sm text-slate-500">Pick a question to see how it was answered.</p>
        )}
      </Card>
    </div>
  );
}
