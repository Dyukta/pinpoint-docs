import { useEffect, useState } from "react";

const POLL_MS = 5000;

export async function* streamEvents(url, body, signal) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw new Error(response.status >= 500 ? "the API is not running" : `HTTP ${response.status}`);
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += value;
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop();
    for (const block of blocks) {
      const kind = block.match(/^event: (.*)$/m)[1];
      const data = JSON.parse(block.match(/^data: (.*)$/m)[1]);
      yield [kind, data];
    }
  }
}

export function usePoll(url) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const response = await fetch(url);
        if (!response.ok) throw new Error(response.status >= 500 ? "offline" : `HTTP ${response.status}`);
        const body = await response.json();
        if (alive) {
          setData(body);
          setError(null);
        }
      } catch (e) {
        if (alive) setError(e.message === "Failed to fetch" ? "offline" : e.message);
      }
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [url]);
  return [data, error];
}
