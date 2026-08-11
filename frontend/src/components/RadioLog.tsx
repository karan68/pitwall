import type { RadioEvent } from "../types";
import { STATE_STYLE } from "../theme";

export default function RadioLog({
  events,
  selectedId,
  onSelect,
}: {
  events: RadioEvent[];
  selectedId: number | null;
  onSelect: (event: RadioEvent) => void;
}) {
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5">
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.15em] text-neutral-400">Radio log</h2>

      {events.length === 0 ? (
        <p className="mt-3 text-xs text-neutral-600">No radio calls analysed yet.</p>
      ) : (
        <ul className="mt-3 flex flex-col gap-1">
          {[...events].reverse().map((event) => {
            const style = STATE_STYLE[event.state];
            const selected = event.id === selectedId;
            return (
              <li key={event.id}>
                <button
                  onClick={() => onSelect(event)}
                  className={`grid w-full grid-cols-[42px_1fr_auto] items-center gap-3 rounded px-2.5 py-2 text-left transition-colors ${
                    selected ? "bg-neutral-800/70" : "hover:bg-neutral-900"
                  }`}
                >
                  <span className="text-xs tabular-nums text-neutral-500">L{event.lap}</span>
                  <span className="truncate text-xs text-neutral-300">
                    {event.transcript || <span className="text-neutral-600">(no speech detected)</span>}
                  </span>
                  <span className="flex items-center gap-2">
                    {event.recommendation.radioWindow === "Closed" && (
                      <span className="text-[9px] font-semibold uppercase tracking-wider text-red-400/70">hold</span>
                    )}
                    <span className="w-14 text-right text-[11px] font-medium" style={{ color: style.dot }}>
                      {event.state}
                    </span>
                    <span className="w-8 text-right text-xs tabular-nums text-neutral-500">{event.driverLoad}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
