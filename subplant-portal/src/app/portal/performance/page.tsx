"use client";
import Swal from "@/lib/swal";

import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { Button } from "@/components/ui/Button";
import { Card, Empty, Stat } from "@/components/ui/bits";
import { TrendingUp, Star, Gauge, AlertTriangle, Info, RefreshCw, Lightbulb } from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

interface PerformanceRecord {
  month_year: string;
  performance_score: number;
  star_rating_num: number;
  efficiency: number;
  utilization: number;
  damage_rate: number;
  total_workload: number;
}

export default function PerformancePage() {
  const [trend, setTrend] = useState<PerformanceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [months, setMonths] = useState<string[]>([]);
  const [month, setMonth] = useState("");
  const [running, setRunning] = useState(false);

  const loadTrend = useCallback(async () => {
    try {
      const r = await api.get("/subplant/performance");
      setTrend(r.data.trend || []);
    } catch { setTrend([]); }
  }, []);

  useEffect(() => {
    const init = async () => {
      try {
        const m = await api.get("/subplant/performance/months");
        const list: string[] = m.data.months || [];
        setMonths(list.length ? list : [m.data.current]);
        setMonth(list[0] || m.data.current);
      } catch { /* ignore */ }
      await loadTrend();
      setLoading(false);
    };
    init();
  }, [loadTrend]);

  // Recompute this plant's score from the gatepasses already recorded.
  const runAnalysis = async () => {
    setRunning(true);
    try {
      const res = await api.post("/subplant/performance/analyze", { month });
      const d = res.data;
      Swal.fire({
        icon: "success",
        title: `Score updated — ${Number(d.performance_score).toFixed(2)} / 5`,
        text: `${month} · ${"★".repeat(d.star_rating_num || 0)} · damage ${d.metrics?.damage_rate}%`,
      });
      await loadTrend();
    } catch (err: unknown) {
      Swal.fire({
        icon: "error", title: "Could not calculate",
        text: getApiErrorMessage(err, "Analysis failed."),
      });
    } finally { setRunning(false); }
  };

  const latest = trend.length ? trend[trend.length - 1] : null;
  const previous = trend.length > 1 ? trend[trend.length - 2] : null;
  const recommendations: Array<{ type: "high" | "medium" | "low" | "good"; text: string }> = [];

  if (latest) {
    if (latest.damage_rate > 3) {
      recommendations.push({
        type: "high",
        text: `Damage rate is ${latest.damage_rate}%, exceeding the 3% limit. Identify and resolve the current quality defects immediately.`,
      });
    } else if (latest.damage_rate > 2) {
      recommendations.push({
        type: "medium",
        text: `Damage rate is ${latest.damage_rate}%, approaching the 3% limit. Reinforce quality checks before it breaches the threshold.`,
      });
    }

    if (previous && latest.damage_rate > previous.damage_rate + 0.5) {
      recommendations.push({
        type: "medium",
        text: `Damage rate increased from ${previous.damage_rate}% last month to ${latest.damage_rate}%. Review recent batches and new styles for quality issues.`,
      });
    }

    const efficiency = latest.efficiency || 0;
    const previousEfficiency = previous?.efficiency || 0;
    if (efficiency < 0.65) {
      recommendations.push({
        type: "high",
        text: `Efficiency is critically low (${Math.round(efficiency * 100)}%). Review line balancing, operator training, and severe production bottlenecks.`,
      });
    } else if (efficiency < 0.75) {
      recommendations.push({
        type: "medium",
        text: `Efficiency is below optimal (${Math.round(efficiency * 100)}%). Review workflows and check for recurring machine downtime.`,
      });
    }

    if (previous && efficiency < previousEfficiency - 0.05) {
      recommendations.push({
        type: "medium",
        text: `Efficiency dropped by ${Math.round((previousEfficiency - efficiency) * 100)}% since last month. Check style complexity and operator readiness.`,
      });
    }

    const utilization = latest.utilization || 0;
    if (utilization < 0.60) {
      recommendations.push({
        type: "low",
        text: `Utilization is very low (${Math.round(utilization * 100)}%). The plant has significant spare capacity and can request more orders.`,
      });
    } else if (utilization < 0.75) {
      recommendations.push({
        type: "low",
        text: `Utilization is ${Math.round(utilization * 100)}%. Production volume can be increased without overloading the plant.`,
      });
    } else if (utilization > 0.95) {
      recommendations.push({
        type: "medium",
        text: `Utilization is extremely high (${Math.round(utilization * 100)}%). Monitor worker fatigue and schedule preventive maintenance.`,
      });
    }

    if (efficiency > 0.85 && utilization < 0.70) {
      recommendations.push({
        type: "good",
        text: `The team is highly efficient (${Math.round(efficiency * 100)}%) while machines are underutilized (${Math.round(utilization * 100)}%). The plant can accept more complex or higher-volume orders.`,
      });
    } else if (efficiency < 0.70 && utilization > 0.90) {
      recommendations.push({
        type: "high",
        text: `Machines are running at ${Math.round(utilization * 100)}% utilization, but efficiency is only ${Math.round(efficiency * 100)}%. Resolve minor stoppages, training gaps, or workflow problems before accepting more work.`,
      });
    }

    if (latest.performance_score >= 4.5) {
      recommendations.push({
        type: "good",
        text: `Outstanding overall performance (${latest.performance_score.toFixed(2)} / 5). The plant is performing as a top-tier FabricFlow partner.`,
      });
    } else if (latest.performance_score < 3.0) {
      recommendations.push({
        type: "high",
        text: `Overall score is low (${latest.performance_score.toFixed(2)} / 5). Prioritize dispatch reliability and damage reduction.`,
      });
    }

    if (recommendations.length === 0) {
      recommendations.push({
        type: "good",
        text: "Performance is optimal across all measured metrics. Keep up the current production practices.",
      });
    }
  }

  return (
    <div className="space-y-6 text-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center">
            <TrendingUp className="w-6 h-6 mr-2 text-teal-600" /> My Performance
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            How FabricFlow scores your plant, based on the gatepasses you record.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-600"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          >
            {months.length === 0 && <option value="">No data</option>}
            {months.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <Button onClick={runAnalysis} disabled={running || !month}
                  className="bg-teal-600 hover:bg-teal-700">
            <RefreshCw className={`w-4 h-4 mr-1 ${running ? "animate-spin" : ""}`} />
            {running ? "Calculating..." : "Calculate My Score"}
          </Button>
        </div>
      </div>

      <div className="rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800 flex items-start gap-2">
        <Info className="w-4 h-4 mt-0.5 shrink-0" />
        <span>
          Scores are calculated monthly from your dispatch records. Recording gatepasses
          promptly and keeping damage below 3% improves your standing against other plants.
        </span>
      </div>

      {loading ? (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center text-slate-500">Loading…</div>
      ) : !latest ? (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
          <p className="text-slate-600 font-medium">No performance score yet.</p>
          <p className="text-sm text-slate-500 mt-1">
            Record gatepasses for a month, then press <strong>Calculate My Score</strong> above.
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Stat icon={<Star className="w-5 h-5" />} label="Latest Score"
                  value={latest.performance_score?.toFixed(2)}
                  sub={`${"★".repeat(latest.star_rating_num || 0)} · ${latest.month_year}`} tone="teal" />
            <Stat icon={<Gauge className="w-5 h-5" />} label="Efficiency"
                  value={`${Math.round((latest.efficiency || 0) * 100)}%`} tone="indigo" />
            <Stat icon={<Gauge className="w-5 h-5" />} label="Utilization"
                  value={`${Math.round((latest.utilization || 0) * 100)}%`} tone="blue" />
            <Stat icon={<AlertTriangle className="w-5 h-5" />} label="Damage Rate"
                  value={`${latest.damage_rate}%`} sub="limit 3.0%"
                  tone={latest.damage_rate > 3 ? "red" : "emerald"} />
          </div>

          <Card title="Performance Score Trend">
            {trend.length > 1 ? (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="month_year" tick={{ fontSize: 11, fill: "#64748b" }} />
                  <YAxis domain={[0, 5]} tick={{ fontSize: 11, fill: "#64748b" }} />
                  <Tooltip contentStyle={{ borderRadius: '8px', color: '#0f172a' }} itemStyle={{ color: '#0f172a' }} /><Legend />
                  <Line type="monotone" dataKey="performance_score" stroke="#0d9488" strokeWidth={2} name="Score" />
                </LineChart>
              </ResponsiveContainer>
            ) : <Empty text="Not enough history to chart yet." />}
          </Card>

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
              <h3 className="font-semibold text-slate-800">Monthly History</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs uppercase text-slate-500 bg-slate-50 border-b border-slate-200">
                  <tr>
                    <th className="px-4 py-3">Month</th>
                    <th className="px-4 py-3 text-right">Score</th>
                    <th className="px-4 py-3 text-right">Efficiency</th>
                    <th className="px-4 py-3 text-right">Utilization</th>
                    <th className="px-4 py-3 text-right">Damage %</th>
                    <th className="px-4 py-3 text-right">Output</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {[...trend].reverse().map((t) => (
                    <tr key={t.month_year} className="hover:bg-slate-50/60">
                      <td className="px-4 py-3 font-medium text-slate-900">{t.month_year}</td>
                      <td className="px-4 py-3 text-right">
                        {t.performance_score?.toFixed(2)}
                        <span className="ml-1 text-amber-500">{"★".repeat(t.star_rating_num || 0)}</span>
                      </td>
                      <td className="px-4 py-3 text-right">{Math.round((t.efficiency || 0) * 100)}%</td>
                      <td className="px-4 py-3 text-right">{Math.round((t.utilization || 0) * 100)}%</td>
                      <td className={`px-4 py-3 text-right font-medium ${t.damage_rate > 3 ? "text-red-600" : "text-emerald-600"}`}>
                        {t.damage_rate}%
                      </td>
                      <td className="px-4 py-3 text-right">{Number(t.total_workload || 0).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {recommendations.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden mt-6">
              <div className="px-6 py-4 border-b border-slate-100 bg-slate-50 flex items-center gap-2">
                <Lightbulb className="w-5 h-5 text-amber-500" />
                <h3 className="font-semibold text-slate-800">Actionable Recommendations</h3>
              </div>
              <div className="p-6 space-y-3">
                {recommendations.map((recommendation, index) => (
                  <div key={index} className={`rounded-lg border p-4 flex items-start gap-3 ${
                    recommendation.type === "high" ? "bg-red-50 text-red-700 border-red-200" :
                    recommendation.type === "medium" ? "bg-amber-50 text-amber-700 border-amber-200" :
                    recommendation.type === "good" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                    "bg-blue-50 text-blue-700 border-blue-200"
                  }`}>
                    <Lightbulb className="w-4 h-4 mt-0.5 shrink-0" />
                    <p className="text-sm font-medium">{recommendation.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
