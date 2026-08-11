import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { LapEntry, RadioEvent } from "../types";

const COLORS: Record<string, string> = {
  Calm: "#34d399",
  Stressed: "#f87171",
  Tired: "#fbbf24",
};

function StressDot(props: { cx?: number; cy?: number; payload?: { color?: string } }) {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null || !payload?.color) return null;
  return <circle cx={cx} cy={cy} r={6} fill={payload.color} stroke="#0a0a0a" strokeWidth={2} />;
}

export default function LapChart({ laps, events }: { laps: LapEntry[]; events: RadioEvent[] }) {
  const eventByLap = new Map(events.map((e) => [e.lap, e]));
  const data = laps.map((l) => {
    const event = eventByLap.get(l.lap);
    return {
      lap: l.lap,
      timeSeconds: l.timeSeconds,
      stressPoint: event ? l.timeSeconds : null,
      color: event ? COLORS[event.label] : undefined,
    };
  });

  return (
    <div className="h-72 w-full rounded-xl border border-neutral-800 bg-neutral-900/60 p-4">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#262626" strokeDasharray="3 3" />
          <XAxis
            dataKey="lap"
            stroke="#737373"
            tickLine={false}
            label={{ value: "Lap", position: "insideBottom", offset: -2, fill: "#737373" }}
          />
          <YAxis stroke="#737373" tickLine={false} domain={["dataMin - 2", "dataMax + 2"]} unit="s" />
          <Tooltip
            contentStyle={{ background: "#171717", border: "1px solid #333", borderRadius: 8 }}
            labelStyle={{ color: "#e5e5e5" }}
          />
          <Line type="monotone" dataKey="timeSeconds" stroke="#60a5fa" strokeWidth={2} dot={false} name="Lap time" />
          <Scatter dataKey="stressPoint" name="Radio call" shape={StressDot} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
