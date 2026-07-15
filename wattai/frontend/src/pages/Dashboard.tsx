import { useQuery } from "@tanstack/react-query";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { Zap, DollarSign, Cpu, AlertTriangle } from "lucide-react";
import api from "../lib/api";

function StatCard({ icon: Icon, label, value, sub, accent }: {
  icon: any; label: string; value: string; sub?: string; accent?: boolean;
}) {
  return (
    <div className={`rounded-xl p-4 border ${accent ? "border-violet-200 bg-violet-50" : "border-gray-100 bg-white"}`}>
      <div className="flex items-center gap-2 mb-1">
        <Icon size={16} className={accent ? "text-violet-500" : "text-gray-400"} />
        <span className="text-xs text-gray-500">{label}</span>
      </div>
      <p className="text-2xl font-medium text-gray-800">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function Dashboard() {
  const { data: live } = useQuery({
    queryKey: ["live"],
    queryFn: () => api.get("/readings/live").then((r) => r.data),
    refetchInterval: 30_000,
  });

  const { data: history } = useQuery({
    queryKey: ["history"],
    queryFn: () => api.get("/readings/history?hours=24").then((r) => r.data),
    refetchInterval: 60_000,
  });

  const { data: sub } = useQuery({
    queryKey: ["sub"],
    queryFn: () => api.get("/subscriptions/status").then((r) => r.data),
  });

  const latest = live?.[0];

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-medium text-gray-800">Live overview</h1>
        {sub?.plan === "free" && (
          <a
            href="/upgrade"
            className="text-xs bg-violet-600 text-white px-3 py-1.5 rounded-lg hover:bg-violet-700 transition-colors"
          >
            Upgrade to Premium
          </a>
        )}
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          icon={Zap}
          label="Active power"
          value={`${latest?.active_power?.toFixed(2) ?? "—"} kW`}
          sub={`${latest?.voltage?.toFixed(0) ?? "—"} V · ${latest?.current_a?.toFixed(1) ?? "—"} A`}
        />
        <StatCard
          icon={Cpu}
          label="Power factor"
          value={latest?.power_factor?.toFixed(2) ?? "—"}
          sub={`${latest?.frequency?.toFixed(1) ?? "—"} Hz`}
        />
        <StatCard
          icon={DollarSign}
          label="Total energy"
          value={`${latest?.forward_energy?.toFixed(1) ?? "—"} kWh`}
          sub="forward (import)"
        />
        <StatCard
          icon={AlertTriangle}
          label="Plan"
          value={sub?.plan === "premium" ? "Premium" : "Free"}
          accent={sub?.plan === "premium"}
          sub={sub?.plan === "premium" ? "AI active" : "Basic monitoring"}
        />
      </div>

      {/* Power chart */}
      <div className="bg-white border border-gray-100 rounded-xl p-4">
        <p className="text-sm font-medium text-gray-600 mb-4">Power — last 24 h</p>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={history ?? []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="time"
              tickFormatter={(t) => t.slice(11, 16)}
              tick={{ fontSize: 11, fill: "#9ca3af" }}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#9ca3af" }}
              unit=" kW"
              width={48}
            />
            <Tooltip
              formatter={(v: number) => [`${v.toFixed(3)} kW`, "Power"]}
              labelFormatter={(l) => l.slice(0, 16).replace("T", " ")}
            />
            <Line
              type="monotone"
              dataKey="kw"
              stroke="#7c3aed"
              strokeWidth={1.5}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Premium gate */}
      {sub?.plan !== "premium" && (
        <div className="border border-violet-100 bg-violet-50 rounded-xl p-5 text-center">
          <p className="text-sm font-medium text-violet-800">AI features require Premium</p>
          <p className="text-xs text-violet-500 mt-1">
            Bill optimisation, appliance detection, and load-pacing advice.
          </p>
          <a
            href="/upgrade"
            className="mt-3 inline-block text-xs bg-violet-600 text-white px-4 py-2 rounded-lg hover:bg-violet-700"
          >
            Upgrade — $9.99 / month
          </a>
        </div>
      )}
    </div>
  );
}
