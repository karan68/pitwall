import type { RadioEvent } from "../types";
import { BIOMARKER_LABELS, STATE_STYLE } from "../theme";

/** The audit trail: every number behind the state, and how far it sits from this driver's normal. */
export default function StateBreakdown({ event }: { event: RadioEvent }) {
  const style = STATE_STYLE[event.state];
  const rows = Object.entries(event.zScores).filter(([key]) => key in BIOMARKER_LABELS);

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-neutral-800 bg-neutral-900/40 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.15em] text-neutral-400">Why this reading</h2>
          <p className={`mt-1 text-sm ${style.text}`}>{event.description}</p>
        </div>
        <span
          className={`shrink-0 rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
            event.confidence.level === "High"
              ? "bg-emerald-500/15 text-emerald-300"
              : event.confidence.level === "Medium"
                ? "bg-amber-500/15 text-amber-300"
                : "bg-neutral-700/40 text-neutral-400"
          }`}
        >
          {event.confidence.level} confidence
        </span>
      </div>

      <p className="text-xs leading-relaxed text-neutral-500">{event.confidence.reason}</p>

      <div className="flex flex-col gap-1.5">
        {rows.map(([key, z]) => {
          const meta = BIOMARKER_LABELS[key];
          const value = event.biomarkers[key as keyof typeof event.biomarkers] as number;
          const magnitude = Math.min(Math.abs(z) / 4, 1) * 50;

          return (
            <div key={key} className="grid grid-cols-[110px_1fr_88px] items-center gap-2" title={meta.meaning}>
              <span className="truncate text-xs text-neutral-400">{meta.label}</span>

              <div className="relative h-4 rounded bg-neutral-900">
                <div className="absolute inset-y-0 left-1/2 w-px bg-neutral-700" />
                <div
                  className="absolute inset-y-[3px] rounded-sm"
                  style={{
                    left: z >= 0 ? "50%" : `${50 - magnitude}%`,
                    width: `${magnitude}%`,
                    background: z >= 0 ? "#f87171" : "#38bdf8",
                    opacity: Math.max(0.35, Math.min(Math.abs(z) / 3, 1)),
                  }}
                />
              </div>

              <span className="text-right text-xs tabular-nums text-neutral-400">
                {value}
                {meta.unit && <span className="text-neutral-600"> {meta.unit}</span>}
                <span className="ml-1 text-neutral-600">
                  {z > 0 ? "+" : ""}
                  {z}σ
                </span>
              </span>
            </div>
          );
        })}
      </div>

      <p className="text-[11px] leading-relaxed text-neutral-600">
        Bars show deviation from this driver's own baseline in standard deviations. Red is above baseline, blue below.
      </p>
    </section>
  );
}
