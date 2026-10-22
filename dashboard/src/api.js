import { useEffect, useState } from "react";

const POLL_MS = 5000;

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
