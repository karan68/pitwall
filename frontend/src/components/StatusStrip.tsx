import type { RadioEvent } from "../types";
import { STATE_STYLE, WINDOW_STYLE } from "../theme";

export default function StatusStrip({ event }: { event: RadioEvent | null }) {
  if (!event) {
    return (
      <div className="grid grid-cols-1 gap-px border-y border-neutral-800 bg-neutral-800 sm:grid-cols-3">
        {["Driver load", "Driver state", "Radio window"].map((label) => (
          <div key={label} className="bg-neutral-950 px-5 py-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-600">{label}</p>
            <p className="mt-1 text-2xl font-semibold text-neutral-700">—</p>
          </div>
        ))}
      </div>
    );
  }

  const state = STATE_STYLE[event.state];
  const window = WINDOW_STYLE[event.recommendation.radioWindow];
  // With no baseline the state is scored against population averages, and the
  // same audio measured out as Tired or Calm depending only on how many
  // calibration clips were accepted. Do not give it the weight of a real reading.
  const provisional = !event.calibrated;

  return (
    <div className="grid grid-cols-1 gap-px border-y border-neutral-800 bg-neutral-800 sm:grid-cols-3">
      <div className="bg-neutral-950 px-5 py-4">
        <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-600">Driver load</p>
        <div className="mt-1 flex items-baseline gap-2">
          <span
            className={`text-3xl font-semibold tabular-nums ${provisional ? "text-neutral-600" : "text-neutral-50"}`}
          >
            {provisional ? "\u2014" : event.driverLoad}
          </span>
          <span className="text-xs text-neutral-500">{provisional ? "needs baseline" : "/ 100"}</span>
        </div>
        <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-neutral-800">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${provisional ? 0 : event.driverLoad}%`,
              background: state.dot,
            }}
          />
        </div>
      </div>

      <div className="bg-neutral-950 px-5 py-4">
        <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-600">Driver state</p>
        {provisional ? (
          <>
            <p className="mt-1 text-3xl font-semibold text-neutral-600">Not calibrated</p>
            <p className="mt-1 text-xs leading-snug text-amber-400/80">
              Provisional reading &ldquo;{event.state}&rdquo; is against population averages, not this driver.
            </p>
          </>
        ) : (
          <>
            <p className={`mt-1 text-3xl font-semibold ${state.text}`}>{event.state}</p>
            <p className="mt-1 text-xs text-neutral-500">
              arousal {event.arousal > 0 ? "+" : ""}
              {event.arousal}σ · strain {event.strain > 0 ? "+" : ""}
              {event.strain}σ
            </p>
          </>
        )}
      </div>

      <div className={`px-5 py-4 ${window.bg}`}>
        <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-500">Radio window</p>
        <div className="mt-1 flex items-center gap-2">
          <span className={`h-3 w-3 shrink-0 rounded-full ${event.recommendation.radioWindow === "Closed" ? "animate-pulse" : ""}`}
            style={{ background: window.text.includes("emerald") ? "#34d399" : window.text.includes("amber") ? "#fbbf24" : "#f87171" }}
          />
          <p className={`text-2xl font-semibold ${window.text}`}>{window.label}</p>
        </div>
        <p className="mt-1 text-xs leading-snug text-neutral-400">{event.recommendation.windowReason}</p>
      </div>
    </div>
  );
}
