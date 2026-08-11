import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Analytics, RadioEvent } from "../types";
import { STATE_STYLE } from "../theme";

export default function LoadLapChart({ analytics, events }: { analytics: Analytics; events: RadioEvent[] }) {
  const stateByLap = new Map(events.map((e) => [e.lap, e.state]));
  const data = analytics.series.map((p) => ({ ...p, state: stateByLap.get(p.lap) }));

  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.15em] text-neutral-400">Driver load vs lap time</h2>
        {analytics.sufficientData && (
          <span className="text-[11px] text-neutral-500">
            r = {analytics.correlation} · {analytics.strength?.toLowerCase()}
          </span>
        )}
      </div>

      <div className="mt-3 h-56">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 6, bottom: 4, left: -14 }}>
            <CartesianGrid stroke="#1f1f1f" />
            <XAxis dataKey="lap" stroke="#525252" tick={{ fontSize: 10 }} tickLine={false} />
            <YAxis
              yAxisId="load"
              domain={[0, 100]}
              stroke="#525252"
              tick={{ fontSize: 10 }}
              tickLine={false}
              width={34}
            />
            <YAxis
              yAxisId="time"
              orientation="right"
              domain={["dataMin - 0.6", "dataMax + 0.6"]}
              stroke="#525252"
              tick={{ fontSize: 10 }}
              tickLine={false}
              width={44}
              tickFormatter={(v: number) => `${v.toFixed(1)}s`}
            />
            <Tooltip
              contentStyle={{ background: "#0a0a0a", border: "1px solid #262626", borderRadius: 6, fontSize: 12 }}
              labelFormatter={(lap) => `Lap ${lap}`}
              formatter={(value: number, name: string) =>
                name === "Lap time" ? [`${value.toFixed(1)}s`, name] : [value, name]
              }
            />
            <Area
              yAxisId="load"
              type="monotone"
              dataKey="load"
              name="Driver load"
              stroke="#f87171"
              strokeWidth={1.5}
              fill="#f87171"
              fillOpacity={0.12}
              connectNulls
            />
            <Line
              yAxisId="time"
              type="monotone"
              dataKey="timeSeconds"
              name="Lap time"
              stroke="#e5e5e5"
              strokeWidth={2}
              dot={(props: unknown) => <LapDot {...(props as LapDotProps)} />}
              activeDot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-neutral-500">{analytics.note}</p>
    </section>
  );
}

interface LapDotProps {
  cx?: number;
  cy?: number;
  key?: string;
  payload?: { measured: boolean; state?: keyof typeof STATE_STYLE };
}

function LapDot({ cx, cy, payload }: LapDotProps) {
  if (cx == null || cy == null || !payload?.measured || !payload.state) return null;
  return <circle cx={cx} cy={cy} r={4.5} fill={STATE_STYLE[payload.state].dot} stroke="#0a0a0a" strokeWidth={1.5} />;
}
