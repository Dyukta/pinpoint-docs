import { ArrowRight, ChevronRight, CircleCheck, CircleHelp, Clock, Zap } from "lucide-react";
import { usePoll } from "../api";
import AskBox from "../components/AskBox";
import TraceTable from "../components/TraceTable";
import { Card, Meter, Stat } from "../components/ui";
import { num, pct, secs } from "../format";

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
        Median seconds per stage. Questions the check refuses skip the answer stage. Tokens per 1,000 questions:{" "}
        {num(stats?.tokens_per_1000.prompt)} in, {num(stats?.tokens_per_1000.output)} out.
      </p>
    </div>
  );
}

export default function SearchPage({ go }) {
  const [stats] = usePoll("/stats?last=200");
  const [latest] = usePoll("/traces?limit=6");
  const answered = stats ? 1 - (stats.refusal_rate ?? 0) - (stats.error_rate ?? 0) : null;

  return (
    <div className="space-y-6">
      <AskBox />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Answered with sources"
          value={pct(answered)}
          hint={`${num(stats?.requests)} questions traced`}
          icon={CircleCheck}
          tone="emerald"
        />
        <Stat
          label="Said I don't know"
          value={pct(stats?.refusal_rate)}
          hint="no grounded answer found"
          icon={CircleHelp}
          tone="amber"
        />
        <Stat
          label="Latency p50"
          value={secs(stats?.latency.p50)}
          hint={`p95 ${secs(stats?.latency.p95)}`}
          icon={Clock}
          tone="violet"
        />
        <Stat
          label="Cache hits"
          value={pct(stats?.cache_hit_rate)}
          hint={`errors ${pct(stats?.error_rate)}`}
          icon={Zap}
          tone="sky"
        />
      </div>
      <div className="grid gap-6 xl:grid-cols-5">
        <Card title="Pipeline" className="xl:col-span-3">
          <Pipeline stats={stats} />
        </Card>
        <Card
          title="Latest questions"
          className="xl:col-span-2"
          action={
            <button
              onClick={() => go("traces")}
              className="flex items-center gap-1 text-sm font-medium text-violet-600 hover:text-violet-700"
            >
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
