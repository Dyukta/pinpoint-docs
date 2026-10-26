import { useEffect, useRef, useState } from "react";
import { streamEvents } from "./api";
import { IDK, secs, topic } from "./format";

const STATUS = {
  search: "Looking through the docs for you...",
  check: "Reading what I found to make sure it fits...",
  "search again": "Hmm, not quite right. Let me look again...",
  answer: "Got it! Writing it up...",
};

function Reply({ reply, now }) {
  const waited = Math.max(0, Math.round((now - reply.start) / 1000));
  const links = reply.sources?.filter((url) => !url.includes("/release-notes/"));
  if (reply.error) return <p className="text-red-400">Sorry, something went wrong: {reply.error}.</p>;
  if (reply.answer === IDK)
    return (
      <p className="text-amber-300">
        <span className="font-semibold">I don't know.</span> I couldn't find this in the FastAPI docs, and I'd rather not guess.
      </p>
    );
  if (!reply.answer)
    return (
      <>
        {reply.draft && <p className="whitespace-pre-wrap leading-relaxed">{reply.draft}</p>}
        <p className={`mt-1 text-zinc-400 ${reply.cancelled ? "" : "animate-pulse"}`}>
          {reply.cancelled ? "Okay, stopped. Ask me something else anytime." : (STATUS[reply.status] ?? "On it...")}
        </p>
        {!reply.cancelled && (
          <p className="mt-1 text-xs text-zinc-500">
            {waited} s{waited >= 15 && " · Thanks for waiting, a careful answer takes a little longer."}
          </p>
        )}
      </>
    );
  return (
    <>
      <p className="whitespace-pre-wrap leading-relaxed">{reply.answer}</p>
      <ul className="mt-3 space-y-1 border-t border-zinc-700 pt-2 text-xs">
        {links.map((url) => (
          <li key={url}>
            <span className="text-zinc-300">{topic(url)}:</span>{" "}
            <a href={url} target="_blank" rel="noreferrer" className="break-all text-red-400 hover:underline">
              {url}
            </a>
          </li>
        ))}
        {links.length === 0 && <li className="text-zinc-400">Only release notes were cited, so check this answer in the docs.</li>}
      </ul>
    </>
  );
}

function TraceLine({ reply }) {
  const t = reply.trace;
  if (!t) return <p className="mt-2 text-xs text-zinc-500">{secs(reply.seconds)}</p>;
  const check = t.agent || !t.answerable ? "NO" : "YES";
  const steps = [
    ["Search", "BM25 + vector search", t.search_seconds],
    ["Check", `Do the sections answer it? ${check}`, t.check_seconds],
    ...(t.agent ? [["Search again", t.agent.query ? `"${t.agent.query}"` : "Model chose not to", t.agent_seconds]] : []),
    ["Answer", t.answer_seconds == null ? "Skipped" : "Written from the sections", t.answer_seconds],
  ];
  return (
    <details className="mt-2 text-xs text-zinc-500">
      <summary className="cursor-pointer hover:text-zinc-300">
        {secs(reply.seconds)}
      </summary>
      <div className="mt-2 space-y-3 border-t border-zinc-700 pt-2">
        {t.cached ? (
          <p>Served from the answer cache: the same question was answered before with the same settings.</p>
        ) : (
          <ol className="space-y-1">
            {steps.map(([name, detail, s]) => (
              <li key={name} className="flex justify-between gap-3">
                <span>
                  <span className="text-zinc-300">{name}</span> · {detail}
                </span>
                <span className="shrink-0 font-mono">{s == null ? "–" : secs(s)}</span>
              </li>
            ))}
          </ol>
        )}
        <div>
          <p className="mb-1 text-zinc-300">Sections found</p>
          <ol className="space-y-1 font-mono">
            {t.retrieved.map((id, i) => (
              <li key={id} className="flex justify-between gap-3">
                <span className="break-all">
                  {i + 1}. {id}
                </span>
                <span className="shrink-0">{t.scores[i]?.toFixed(4)}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </details>
  );
}

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [agent, setAgent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());
  const controller = useRef(null);
  const end = useRef(null);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (!busy) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [busy]);

  const patch = (change) => setMessages((list) => [...list.slice(0, -1), { ...list.at(-1), ...change }]);

  const ask = async (e) => {
    e.preventDefault();
    const text = question.trim();
    if (text.length < 3 || busy) return;
    setQuestion("");
    setBusy(true);
    const start = Date.now();
    setNow(start);
    setMessages((list) => [...list, { question: text, draft: "", start }]);
    controller.current = new AbortController();
    try {
      for await (const [kind, data] of streamEvents("/ask/stream", { question: text, agent }, controller.current.signal)) {
        if (kind === "status") patch({ status: data });
        if (kind === "token") setMessages((list) => [...list.slice(0, -1), { ...list.at(-1), draft: list.at(-1).draft + data }]);
        if (kind === "done") {
          patch({ ...data, seconds: (Date.now() - start) / 1000 });
          const detail = await fetch(`/traces/${data.trace_id}`, { signal: controller.current.signal });
          if (detail.ok) patch({ trace: await detail.json() });
        }
      }
    } catch (err) {
      patch(err.name === "AbortError" ? { cancelled: true } : { error: err.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-6 overflow-y-auto px-5 py-6 text-sm">
        {messages.length === 0 && <p className="grid h-full place-items-center text-zinc-400">Hi! Ask me anything about the FastAPI docs.</p>}
        {messages.map((m, i) => (
          <div key={i} className="space-y-2">
            <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-red-600 px-3 py-2 text-white">{m.question}</p>
            <div className="w-fit max-w-[85%] rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2">
              <Reply reply={m} now={now} />
              {m.seconds && <TraceLine reply={m} />}
            </div>
          </div>
        ))}
        {messages.length > 0 && <div ref={end} />}
      </div>
      <form onSubmit={ask} className="border-t border-zinc-800 px-5 py-3">
        <div className="flex gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm focus:border-red-500 focus:outline-none"
          />
          {busy ? (
            <button key="cancel" type="button" onClick={() => controller.current.abort()} className="rounded-lg border border-zinc-700 px-4 text-sm hover:bg-zinc-800">
              Cancel
            </button>
          ) : (
            <button
              key="send"
              disabled={question.trim().length < 3}
              title="Type at least 3 characters"
              className="rounded-lg bg-red-600 px-4 text-sm text-white hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-red-600"
            >
              Send
            </button>
          )}
        </div>
        <label className="mt-2 flex items-center gap-1.5 text-xs text-zinc-300">
          <input type="checkbox" checked={agent} onChange={(e) => setAgent(e.target.checked)} className="accent-red-600" />
          Search again if the first search misses (slower)
        </label>
      </form>
    </div>
  );
}
