import type { RadioEvent } from "../types";

const STYLES: Record<string, { bg: string; text: string; emoji: string }> = {
  Calm: { bg: "bg-emerald-500/15", text: "text-emerald-400", emoji: "🟢" },
  Stressed: { bg: "bg-red-500/15", text: "text-red-400", emoji: "🔴" },
  Tired: { bg: "bg-amber-500/15", text: "text-amber-400", emoji: "🟡" },
};

export default function MoodBadge({ event }: { event: RadioEvent }) {
  const style = STYLES[event.label] ?? STYLES.Calm;

  return (
    <div className="flex flex-col gap-3">
      <div
        className={`inline-flex w-fit items-center gap-2 rounded-full px-4 py-1.5 text-sm font-semibold ${style.bg} ${style.text}`}
      >
        <span>{style.emoji}</span>
        <span>{event.label}</span>
        <span className="text-xs opacity-70">
          ({event.rawEmotion}, {event.confidence}%)
        </span>
      </div>

      <div>
        <div className="mb-1 flex justify-between text-xs text-neutral-400">
          <span>Stress index</span>
          <span>{event.stressIndex}/100</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-800">
          <div
            className="h-full rounded-full bg-gradient-to-r from-emerald-500 via-amber-500 to-red-500"
            style={{ width: `${event.stressIndex}%` }}
          />
        </div>
      </div>
    </div>
  );
}
