import type { RadioEvent } from "../types";

const STATUS = {
  agree: { label: "Channels agree", text: "text-emerald-300", bg: "bg-emerald-500/10" },
  "voice-only": { label: "Voice only", text: "text-amber-300", bg: "bg-amber-500/10" },
  "inputs-only": { label: "Inputs only", text: "text-sky-300", bg: "bg-sky-500/10" },
  unavailable: { label: "No telemetry", text: "text-neutral-500", bg: "bg-neutral-800/40" },
} as const;

/** A second, independent channel: how the car was actually being driven on the lap the
 *  radio was transmitted. Kept as corroboration, never folded into the state score —
 *  traffic and tyres roughen inputs just as readily as the driver does. */
export default function DrivingCrossCheck({ event }: { event: RadioEvent }) {
  const check = event.drivingCrossCheck;
  if (!check) return null;

  const style = STATUS[check.status];
  const roughness = event.drivingRoughness;

  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.15em] text-neutral-400">
          Cross-check: driver inputs
        </h2>
        <span
          className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${style.bg} ${style.text}`}
        >
          {style.label}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div className="rounded border border-neutral-800 bg-neutral-950 p-3">
          <p className="text-[10px] uppercase tracking-wider text-neutral-600">Voice says</p>
          <p className="mt-0.5 text-lg font-semibold text-neutral-200">load {event.driverLoad}</p>
          <p className="text-[10px] text-neutral-600">from the radio call</p>
        </div>
        <div className="rounded border border-neutral-800 bg-neutral-950 p-3">
          <p className="text-[10px] uppercase tracking-wider text-neutral-600">Driving says</p>
          <p className={`mt-0.5 text-lg font-semibold ${style.text}`}>
            {roughness == null ? "—" : `${roughness > 0 ? "+" : ""}${roughness}σ`}
          </p>
          <p className="text-[10px] text-neutral-600">throttle & brake activity, lap {event.lap}</p>
        </div>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-neutral-500">{check.detail}</p>
    </section>
  );
}
