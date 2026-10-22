export const IDK = "I don't know.";

export const pct = (x) => `${Math.round((x ?? 0) * 100)}%`;
export const secs = (x) => `${(x ?? 0).toFixed(1)} s`;
export const num = (x) => (x ?? 0).toLocaleString();
export const section = (url) => url.replace("https://fastapi.tiangolo.com/", "").replace(/\/$/, "") || "home";
export const firstLine = (text) => text.split("\n")[0];
