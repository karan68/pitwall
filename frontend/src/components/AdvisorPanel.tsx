import type { RadioEvent } from "../types";

export default function AdvisorPanel({ event }: { event: RadioEvent }) {
  const { recommendation, content } = event;

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-neutral-800 bg-neutral-900/40 p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.15em] text-neutral-400">Engineer call</h2>
        <div className="flex items-center gap-1.5">
          <span className="rounded bg-neutral-800 px-2 py-0.5 text-[10px] font-medium text-neutral-300">
            {content.intent}
          </span>
          <span
            className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
              content.priority === "Critical"
                ? "bg-red-500/20 text-red-300"
                : content.priority === "Strategic"
                  ? "bg-amber-500/15 text-amber-300"
                  : "bg-neutral-800 text-neutral-400"
            }`}
          >
            {content.priority}
          </span>
        </div>
      </div>

      <div>
        <p className="text-base font-medium leading-snug text-neutral-100">{recommendation.action.headline}</p>
        <p className="mt-1.5 text-xs leading-relaxed text-neutral-500">{recommendation.action.rationale}</p>
      </div>

      {recommendation.flags.length > 0 && (
        <div className="flex flex-col gap-2 border-t border-neutral-800 pt-3">
          {recommendation.flags.map((flag) => (
            <div
              key={flag.title}
              className={`rounded border-l-2 py-1 pl-3 ${
                flag.level === "warning" ? "border-amber-500 bg-amber-500/5" : "border-neutral-700 bg-neutral-900/60"
              }`}
            >
              <p
                className={`text-xs font-semibold ${
                  flag.level === "warning" ? "text-amber-300" : "text-neutral-400"
                }`}
              >
                {flag.title}
              </p>
              <p className="mt-0.5 text-[11px] leading-relaxed text-neutral-500">{flag.detail}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
