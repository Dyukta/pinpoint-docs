import { firstLine, secs } from "../format";
import { Verdict } from "./ui";

export default function TraceTable({ traces, onPick, picked }) {
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
