import { usePoll } from "./api";
import { pct, secs } from "./format";

const FAILURES = {
  search_missed_gold: "Search missed the right page",
  refused_with_gold: "Right page found, check said NO",
  answered_unanswerable: "Answered an out-of-scope question",
  cited_wrong_page: "Linked the wrong page",
};

const outOfScope = (run) =>
  Object.entries(run.by_tag)
    .filter(([tag]) => tag !== "docs")
    .reduce((sum, [, t]) => ({ passed: sum.passed + t.passed, total: sum.total + t.total }), { passed: 0, total: 0 });

const ROWS = [
  ["All questions passed", (run) => ({ passed: run.passed, total: run.questions })],
  ["Out of scope: said I don't know", outOfScope],
  ["Docs: answered with the right link", (run) => run.by_tag.docs],
];

const score = ({ passed, total }) => `${passed}/${total}`;

function Rows({ items }) {
  return (
    <ul className="space-y-1">
      {items.map(([label, value]) => (
        <li key={label} className="flex justify-between gap-3">
          <span className="text-zinc-300">{label}</span>
          <span className="font-mono">{value}</span>
        </li>
      ))}
    </ul>
  );
}

export default function Analytics({ onClose }) {
  const [run, runError] = usePoll("/eval");
  const [live, liveError] = usePoll("/stats");

  return (
    <aside className="fixed inset-y-0 right-0 z-10 w-full max-w-sm overflow-y-auto border-l border-zinc-800 bg-zinc-950 p-5 text-sm text-white shadow-2xl">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Analytics</h2>
        <button onClick={onClose} className="rounded-lg border border-zinc-700 px-3 py-1 text-xs hover:bg-zinc-800">
          Close
        </button>
      </div>

      <h3 className="mb-1 font-medium">Test results</h3>
      {runError && <p className="text-zinc-400">Couldn't load test results: {runError}.</p>}
      {run && (
        <>
          <p className="mb-2 text-xs text-zinc-400">{run.questions} held-out questions, run once at the end.</p>
          <table className="w-full text-left">
            <thead className="text-xs text-zinc-400">
              <tr>
                <th className="py-1 font-normal" />
                <th className="font-normal">With check</th>
                <th className="font-normal">Without</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map(([label, pick]) => (
                <tr key={label} className="border-t border-zinc-800">
                  <td className="py-2 pr-2 text-zinc-300">{label}</td>
                  <td className="font-mono">{score(pick(run))}</td>
                  <td className="font-mono text-zinc-400">{run.without_check ? score(pick(run.without_check)) : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3 className="mb-2 mt-6 font-medium">What still fails</h3>
          <Rows items={Object.entries(run.failures).map(([kind, n]) => [FAILURES[kind] ?? kind, n])} />
        </>
      )}

      <h3 className="mb-2 mt-6 font-medium">Live{live && `, last ${live.requests} requests`}</h3>
      {liveError && <p className="text-zinc-400">Couldn't load live numbers: {liveError}.</p>}
      {live && (
        <Rows
          items={[
            ["Median answer time", secs(live.latency.p50)],
            ["Slowest 5% take over", secs(live.latency.p95)],
            ["Said I don't know", pct(live.refusal_rate)],
            ["Served from cache", pct(live.cache_hit_rate)],
            ["Errors", pct(live.error_rate)],
          ]}
        />
      )}
    </aside>
  );
}
