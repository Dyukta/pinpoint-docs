export const IDK = "I don't know.";

export const pct = (x) => `${Math.round((x ?? 0) * 100)}%`;
export const secs = (x) => `${(x ?? 0).toFixed(1)} s`;
export const num = (x) => (x ?? 0).toLocaleString();
export const topic = (url) => {
  const name = new URL(url).hash.slice(1) || url.split("/").filter(Boolean).pop();
  return name.replace(/-/g, " ").replace(/^./, (c) => c.toUpperCase());
};
export const firstLine = (text) => text.split("\n")[0];
