import { BookOpenCheck, CircleHelp, Clock, Crosshair, Loader2, ShieldCheck } from "lucide-react";
import { usePoll } from "../api";
import { Card, Meter, Stat } from "../components/ui";
import { pct, secs } from "../format";

const FAILURES = {
  search_missed_gold: "Search missed the right page",
  refused_with_gold: "Refused, though the right page was found",
  answered_unanswerable: "Answered a question the docs do not cover",
  cited_wrong_page: "Cited the wrong page",
  error: "Error",
};

const docs = (r) => r.by_tag.docs ?? { passed: 0, total: 0 };
const other = (r) =>
  Object.entries(r.by_tag)
    .filter(([tag]) => tag !== "docs")
    .reduce((a, [, v]) => ({ passed: a.passed + v.passed, total: a.total + v.total }), { passed: 0, total: 0 });

const ROWS = [
  ["Passed", (r) => `${r.passed} / ${r.questions}`],
  ["Docs questions: cited the right page", (r) => `${docs(r).passed} / ${docs(r).total}`],
  ["Other questions: said I don't know", (r) => `${other(r).passed} / ${other(r).total}`],
  ["Said I don't know overall", (r) => pct(r.refusal_rate)],
  ["Latency p50 / p95", (r) => `${secs(r.latency.p50)} / ${secs(r.latency.p95)}`],
];

function Compare({ run, base }) {
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
        {ROWS.map(([label, value]) => (
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

function Bars({ items, tone }) {
  return (
    <div className="space-y-4">
      {items.map(({ key, label, detail, value, max }) => (
        <div key={key}>
          <div className="mb-1 flex justify-between text-sm">
            <span className="text-slate-700">{label}</span>
            <span className="text-slate-500">{detail}</span>
          </div>
          <Meter value={value} max={max} tone={tone} />
        </div>
      ))}
    </div>
  );
}

export default function Evaluation() {
  const [run, error] = usePoll("/eval");
  if (error) {
    return (
      <Card title="Evaluation">
        <p className="text-sm text-slate-500">No test run found ({error}).</p>
      </Card>
    );
  }
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
        <div className="flex-1 text-base font-semibold">
          {run.passed} of {run.questions} held-out questions passed with the abstention check
          {base && <span className="text-indigo-200">, {base.passed} without it</span>}
        </div>
      </section>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Passed"
          value={`${run.passed} / ${run.questions}`}
          hint="held-out test"
          icon={BookOpenCheck}
          tone="violet"
        />
        <Stat
          label="Docs questions"
          value={`${docs(run).passed} / ${docs(run).total}`}
          hint="cited the right page"
          icon={Crosshair}
          tone="emerald"
        />
        <Stat
          label="Said I don't know"
          value={pct(run.refusal_rate)}
          hint="of all test questions"
          icon={CircleHelp}
          tone="amber"
        />
        <Stat
          label="Latency p95"
          value={secs(run.latency.p95)}
          hint={`p50 ${secs(run.latency.p50)}`}
          icon={Clock}
          tone="sky"
        />
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        {base && (
          <Card title="With and without the check">
            <Compare run={run} base={base} />
          </Card>
        )}
        <Card title="What still fails">
          <Bars
            tone="from-rose-400 to-rose-500"
            items={failures.map(([kind, n]) => ({
              key: kind,
              label: FAILURES[kind] ?? kind,
              detail: n,
              value: n,
              max: most,
            }))}
          />
        </Card>
        <Card title="By question type" className="xl:col-span-2">
          <Bars
            items={Object.entries(run.by_tag).map(([tag, v]) => ({
              key: tag,
              label: tag,
              detail: `${v.passed} / ${v.total} passed`,
              value: v.passed,
              max: v.total,
            }))}
          />
        </Card>
      </div>
    </div>
  );
}
