import { useRef, useState } from "react";
import { CircleSlash, Loader2, Search } from "lucide-react";
import { streamEvents } from "../api";
import { IDK, section } from "../format";
import { Steps } from "./ui";

const STATUS = {
  search: "Searching the docs...",
  check: "Checking whether the excerpts answer it...",
  "search again": "The first search did not answer it, so the model is searching again...",
  answer: "Writing the answer...",
};

export default function AskBox() {
  const [question, setQuestion] = useState("");
  const [agent, setAgent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [trace, setTrace] = useState(null);
  const controller = useRef(null);

  const ask = async (e) => {
    e.preventDefault();
    if (question.trim().length < 3 || busy) return;
    setBusy(true);
    setStatus(null);
    setDraft("");
    setError(null);
    setResult(null);
    setTrace(null);
    controller.current = new AbortController();
    const { signal } = controller.current;
    try {
      for await (const [kind, data] of streamEvents("/ask/stream", { question, agent }, signal)) {
        if (kind === "status") setStatus(data);
        if (kind === "token") setDraft((text) => text + data);
        if (kind === "done") {
          setResult(data);
          const detail = await fetch(`/traces/${data.trace_id}`, { signal });
          if (detail.ok) setTrace(await detail.json());
        }
      }
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
      <label className="mt-3 flex items-center gap-2 text-sm text-indigo-100">
        <input type="checkbox" checked={agent} onChange={(e) => setAgent(e.target.checked)} />
        Search again if the first search does not answer it (experimental, slower)
      </label>
      {busy && !result && (
        <div className="mt-4 space-y-3">
          <p className="text-sm text-indigo-100">{STATUS[status] ?? "Sending..."}</p>
          {draft && (
            <pre className="whitespace-pre-wrap break-words rounded-xl bg-white/10 p-4 font-sans text-sm leading-relaxed">
              {draft}
            </pre>
          )}
        </div>
      )}
      {error && <p className="mt-4 text-sm text-rose-200">Request failed: {error}.</p>}
      {result && (
        <div className="mt-5 grid gap-4 lg:grid-cols-5">
          <div className={`rounded-xl bg-white/10 p-4 lg:col-span-3 ${abstained ? "flex items-center" : ""}`}>
            {abstained ? (
              <div className="flex gap-3">
                <CircleSlash size={20} className="mt-0.5 shrink-0 text-amber-200" />
                <div>
                  <div className="font-semibold">I don't know.</div>
                  <div className="mt-1 text-sm text-indigo-100">
                    The retrieved sections do not answer this, so Pinpoint does not guess.
                  </div>
                </div>
              </div>
            ) : (
              <>
                <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{result.answer}</pre>
                <div className="mt-4 text-xs font-semibold uppercase tracking-wider text-indigo-200">Grounded in</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {result.sources.map((url) => (
                    <a
                      key={url}
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-full bg-white/15 px-3 py-1 text-xs hover:bg-white/25"
                    >
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
