import { IDK, secs } from "../format";

const TONES = {
  violet: "bg-violet-100 text-violet-600",
  amber: "bg-amber-100 text-amber-600",
  rose: "bg-rose-100 text-rose-600",
  emerald: "bg-emerald-100 text-emerald-600",
  sky: "bg-sky-100 text-sky-600",
};

export function Card({ title, action, children, footer, scroll = false, className = "" }) {
  return (
    <section className={`rounded-2xl border border-slate-200 bg-white p-6 shadow-sm ${scroll ? "flex min-h-0 flex-col" : ""} ${className}`}>
      {(title || action) && (
        <div className="mb-5 flex items-start justify-between gap-4">
          <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          {action}
        </div>
      )}
      {scroll ? <div className="min-h-0 flex-1 scroll-theme overflow-y-auto overflow-x-hidden pr-4">{children}</div> : children}
      {footer}
    </section>
  );
}

export function Stat({ label, value, hint, icon: Icon, tone }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <span className="text-sm text-slate-500">{label}</span>
        <span className={`rounded-xl p-2 ${TONES[tone]}`}>
          <Icon size={18} />
        </span>
      </div>
      <div className="mt-2 text-3xl font-semibold text-slate-900">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export function Meter({ value, max, tone = "from-violet-500 to-indigo-500" }) {
  const width = max ? Math.max(3, (value / max) * 100) : 0;
  return (
    <div className="h-2 rounded-full bg-slate-100">
      <div className={`h-2 rounded-full bg-gradient-to-r ${tone}`} style={{ width: `${width}%` }} />
    </div>
  );
}

export function Verdict({ trace }) {
  const [text, style] = trace.error
    ? ["Error", "bg-rose-100 text-rose-700"]
    : trace.cached
      ? ["Cached", "bg-sky-100 text-sky-700"]
      : trace.answer === IDK
        ? ["I don't know", "bg-amber-100 text-amber-700"]
        : ["Answered", "bg-violet-100 text-violet-700"];
  return <span className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>{text}</span>;
}

export function Steps({ trace, dark = false }) {
  const muted = dark ? "text-indigo-200" : "text-slate-500";
  const strong = dark ? "text-white" : "text-slate-800";
  if (trace.cached) {
    return (
      <p className={`text-sm ${muted}`}>
        Served from the answer cache: an almost identical question was answered before with the same settings.
      </p>
    );
  }
  const steps = [
    ["Retrieve", "BM25 + vector search, fused with RRF", trace.search_seconds],
    ["Check", trace.answerable ? "Excerpts answer it: YES" : "Excerpts answer it: NO", trace.check_seconds],
    ["Answer", trace.answer_seconds == null ? "Skipped" : "Grounded answer with links", trace.answer_seconds],
  ];
  const max = Math.max(...steps.map(([, , s]) => s ?? 0), 0.1);
  const badge = dark ? "bg-white/20 text-white" : "bg-violet-100 text-violet-700";
  const bar = dark ? "bg-white/80" : "bg-gradient-to-r from-violet-500 to-indigo-500";
  return (
    <ol className="space-y-3">
      {steps.map(([name, detail, s], i) => (
        <li key={name} className="grid grid-cols-[1.75rem_minmax(0,1fr)_3.5rem] items-center gap-3 text-sm">
          <span className={`grid h-7 w-7 place-items-center rounded-full text-xs font-semibold ${badge}`}>{i + 1}</span>
          <div>
            <div className="mb-1 flex justify-between gap-2">
              <span className={`font-medium ${strong}`}>{name}</span>
              <span className={`text-xs ${muted}`}>{detail}</span>
            </div>
            <div className={`h-2 rounded-full ${dark ? "bg-white/15" : "bg-slate-100"}`}>
              <div
                className={`h-2 rounded-full ${s == null ? "bg-transparent" : bar}`}
                style={{ width: `${s == null ? 0 : Math.max(3, (s / max) * 100)}%` }}
              />
            </div>
          </div>
          <span className={`text-right font-mono text-xs ${muted}`}>{secs(s)}</span>
        </li>
      ))}
    </ol>
  );
}
