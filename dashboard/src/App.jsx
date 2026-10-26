import { useState } from "react";
import Analytics from "./Analytics";
import Chat from "./Chat";

export default function App() {
  const [analytics, setAnalytics] = useState(false);

  return (
    <div className="flex h-screen justify-center p-4 font-sans text-white sm:p-8">
      <div className="flex w-full max-w-3xl flex-col rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
          <h1 className="text-lg font-semibold">
            Pinpoint<span className="text-red-500">.</span>
          </h1>
          <button onClick={() => setAnalytics(true)} className="rounded-lg border border-zinc-700 px-3 py-1 text-xs hover:bg-zinc-800">
            View analytics
          </button>
        </div>
        <Chat />
      </div>
      {analytics && <Analytics onClose={() => setAnalytics(false)} />}
    </div>
  );
}
