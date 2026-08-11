import {
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import type { RadioEvent } from "../types";
import { STATE_STYLE } from "../theme";

// Positions match the axes: strain runs left(-) to right(+), arousal bottom(-) to top(+).
const QUADRANTS = [
  { x: "72%", y: "16%", label: "STRESSED", hint: "effort + strain", color: "#f87171" },
  { x: "20%", y: "16%", label: "LOCKED IN", hint: "effort, clean voice", color: "#38bdf8" },
  { x: "72%", y: "78%", label: "TIRED", hint: "strain, no effort", color: "#fbbf24" },
  { x: "20%", y: "78%", label: "CALM", hint: "near baseline", color: "#34d399" },
];

/** Arousal and strain are plotted separately because collapsing them loses the distinction
 *  between a driver who is attacking and one who is drowning. */
export default function QuadrantChart({
  events,
  selectedId,
}: {
  events: RadioEvent[];
  selectedId: number | null;
}) {
  const highlightId = selectedId ?? events.at(-1)?.id ?? null;

  const points = events.map((e) => ({
    arousal: e.arousal,
    strain: e.strain,
    lap: e.lap,
    state: e.state,
    fill: STATE_STYLE[e.state].dot,
    size: e.id === highlightId ? 220 : 90,
    opacity: e.id === highlightId ? 1 : 0.35,
  }));

  return (
    <section className="relative rounded-lg border border-neutral-800 bg-neutral-900/40 p-5">
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.15em] text-neutral-400">Arousal × strain</h2>
      <p className="mt-1 text-xs text-neutral-500">Each radio call, positioned against this driver's baseline.</p>

      <div className="relative mt-3 h-64">
        {QUADRANTS.map((q) => (
          <div key={q.label} className="pointer-events-none absolute z-10 -translate-x-1/2" style={{ left: q.x, top: q.y }}>
            <p className="text-[10px] font-semibold tracking-[0.12em]" style={{ color: q.color, opacity: 0.75 }}>
              {q.label}
            </p>
            <p className="text-[9px] text-neutral-600">{q.hint}</p>
          </div>
        ))}

        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 10, right: 12, bottom: 18, left: -18 }}>
            <CartesianGrid stroke="#1f1f1f" />
            <XAxis
              type="number"
              dataKey="strain"
              domain={[-4, 4]}
              ticks={[-4, -2, 0, 2, 4]}
              stroke="#525252"
              tick={{ fontSize: 10 }}
              label={{ value: "vocal strain (σ)", position: "insideBottom", offset: -10, fill: "#525252", fontSize: 10 }}
            />
            <YAxis
              type="number"
              dataKey="arousal"
              domain={[-4, 4]}
              ticks={[-4, -2, 0, 2, 4]}
              stroke="#525252"
              tick={{ fontSize: 10 }}
              label={{ value: "arousal (σ)", angle: -90, position: "insideLeft", offset: 22, fill: "#525252", fontSize: 10 }}
            />
            <ZAxis type="number" dataKey="size" range={[90, 220]} />
            <ReferenceLine x={0.6} stroke="#3f3f46" strokeDasharray="4 4" />
            <ReferenceLine y={0.6} stroke="#3f3f46" strokeDasharray="4 4" />
            <Tooltip
              cursor={{ stroke: "#404040" }}
              contentStyle={{ background: "#0a0a0a", border: "1px solid #262626", borderRadius: 6, fontSize: 12 }}
              formatter={(value, name) => [`${value}σ`, String(name)]}
              labelFormatter={() => ""}
            />
            <Scatter data={points} shape={(props: unknown) => <Dot {...(props as DotProps)} />} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

interface DotProps {
  cx?: number;
  cy?: number;
  payload?: { fill: string; opacity: number; lap: number };
}

function Dot({ cx, cy, payload }: DotProps) {
  if (cx == null || cy == null || !payload) return null;
  const isLatest = payload.opacity === 1;
  return (
    <g>
      {isLatest && <circle cx={cx} cy={cy} r={11} fill={payload.fill} opacity={0.2} />}
      <circle cx={cx} cy={cy} r={isLatest ? 6 : 4} fill={payload.fill} opacity={payload.opacity} stroke="#0a0a0a" strokeWidth={1.5} />
      {isLatest && (
        <text x={cx} y={cy - 15} textAnchor="middle" fill="#a3a3a3" fontSize={10}>
          L{payload.lap}
        </text>
      )}
    </g>
  );
}
