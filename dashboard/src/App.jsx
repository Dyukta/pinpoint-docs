import { useState } from "react";
import { usePoll } from "./api";
import Evaluation from "./pages/Evaluation";
import SearchPage from "./pages/SearchPage";
import Traces from "./pages/Traces";

const PAGES = {
  search: { label: "Search", view: SearchPage },
  traces: { label: "Traces", view: Traces },
  evaluation: { label: "Evaluation", view: Evaluation },
};

function ApiStatus() {
  const [, error] = usePoll("/stats?last=1");
  return (
    <div className="flex items-center gap-2 rounded-xl bg-white/5 p-3 text-sm font-medium text-white">
      <span className={`h-2 w-2 rounded-full ${error ? "bg-rose-400" : "bg-emerald-400"}`} />
      {error ? "API not connected" : "API connected"}
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState("search");
  const { label, view: View } = PAGES[page];

  return (
    <div className="flex min-h-screen bg-[#f4f3fb] font-sans text-slate-800">
      <aside className="sticky top-0 flex h-screen w-64 shrink-0 flex-col bg-gradient-to-b from-[#221a5c] to-[#15103d] p-4 text-indigo-100">
        <div className="mb-6 px-3 py-1 text-xl font-semibold text-white">Pinpoint</div>
        <nav className="flex-1">
          {Object.entries(PAGES).map(([key, item]) => (
            <button
              key={key}
              onClick={() => setPage(key)}
              className={`mb-1 flex w-full items-center rounded-xl px-3 py-2.5 text-left font-medium ${key === page ? "bg-violet-600 text-white shadow" : "hover:bg-white/5"}`}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <ApiStatus />
      </aside>
      <main className="flex-1 overflow-x-hidden px-6 py-8 lg:px-10">
        <h1 className="mb-6 text-3xl font-semibold text-slate-900">{label}</h1>
        <View go={setPage} />
      </main>
    </div>
  );
}
