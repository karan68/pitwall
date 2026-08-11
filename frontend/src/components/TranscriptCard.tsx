import type { RadioEvent } from "../types";

export default function TranscriptCard({ event }: { event: RadioEvent }) {
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4">
      <p className="mb-1 text-xs uppercase tracking-wide text-neutral-500">
        Radio transcript · Lap {event.lap}
      </p>
      <p className="text-lg text-neutral-100">
        "{event.transcript || "(no speech detected)"}"
      </p>
    </div>
  );
}
