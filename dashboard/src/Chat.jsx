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
        {reply.sources.map((url) => (
          <li key={url}>
            <span className="text-zinc-300">{topic(url)}:</span>{" "}
            <a href={url} target="_blank" rel="noreferrer" className="break-all text-red-400 hover:underline">
              {url}
            </a>
          </li>
        ))}
      </ul>
    </>
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
        if (kind === "done") patch({ ...data, seconds: (Date.now() - start) / 1000 });
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
        {messages.length === 0 && <p className="text-center text-zinc-400">Hi! Ask me anything about the FastAPI docs.</p>}
        {messages.map((m, i) => (
          <div key={i} className="space-y-2">
            <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-red-600 px-3 py-2 text-white">{m.question}</p>
            <div className="w-fit max-w-[85%] rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2">
              <Reply reply={m} now={now} />
              {m.seconds && <p className="mt-2 text-xs text-zinc-500">Answered in {secs(m.seconds)}</p>}
            </div>
          </div>
        ))}
        <div ref={end} />
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
            <button key="send" className="rounded-lg bg-red-600 px-4 text-sm text-white hover:bg-red-500">
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
