import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";

export default function EnergyCurves({ energyCurve, fatigueCurve }) {
  if (!energyCurve?.length && !fatigueCurve?.length) return null;

  // merge into unified array keyed by time
  const map = new Map();
  energyCurve?.forEach(({ time, value }) => {
    if (!map.has(time)) map.set(time, { time });
    map.get(time).energy = +(value * 100).toFixed(1);
  });
  fatigueCurve?.forEach(({ time, value }) => {
    if (!map.has(time)) map.set(time, { time });
    map.get(time).fatigue = +(value * 100).toFixed(1);
  });
  const data = [...map.values()].sort((a, b) => a.time.localeCompare(b.time));

  return (
    <div className="w-full h-[260px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
          <defs>
            <linearGradient id="gradEnergy" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--chart-1)" stopOpacity={0.35} />
              <stop offset="95%" stopColor="var(--chart-1)" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="gradFatigue" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--chart-3)" stopOpacity={0.35} />
              <stop offset="95%" stopColor="var(--chart-3)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 6" stroke="var(--border)" />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{
              background: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              fontSize: 12,
            }}
            formatter={(v) => `${v}%`}
          />
          <Legend
            wrapperStyle={{ fontSize: 12 }}
            iconType="circle"
            iconSize={8}
          />
          <Area
            type="monotone"
            dataKey="energy"
            name="Energy"
            stroke="var(--chart-1)"
            strokeWidth={2}
            fill="url(#gradEnergy)"
          />
          <Area
            type="monotone"
            dataKey="fatigue"
            name="Fatigue"
            stroke="var(--chart-3)"
            strokeWidth={2}
            fill="url(#gradFatigue)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
