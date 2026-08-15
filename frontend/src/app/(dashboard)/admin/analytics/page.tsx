"use client";
import Swal from "@/lib/swal";

import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import {
  Activity, Trophy, Clock, AlertTriangle, Zap, RefreshCw, Star,
  TrendingUp, Gauge, Lightbulb, BarChart3,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";

const TABS = ["Overview", "KPI Comparison", "Delay & Damage", "Workload", "Recommendations"] as const;
type Tab = (typeof TABS)[number];

const BAND_STYLE: Record<string, string> = {
  Excellent: "bg-emerald-100 text-emerald-700 border-emerald-200",
  "Very Good": "bg-green-100 text-green-700 border-green-200",
  Acceptable: "bg-amber-100 text-amber-700 border-amber-200",
  "Needs Improvement": "bg-red-100 text-red-700 border-red-200",
  Unknown: "bg-slate-100 text-slate-600 border-slate-200",
};

const STATUS_STYLE: Record<string, string> = {
  Underutilized: "bg-blue-100 text-blue-700 border-blue-200",
  Optimal: "bg-emerald-100 text-emerald-700 border-emerald-200",
  Overloaded: "bg-red-100 text-red-700 border-red-200",
};

const PRIORITY_STYLE: Record<string, string> = {
  high: "bg-red-50 text-red-700 border-red-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  low: "bg-slate-50 text-slate-600 border-slate-200",
};


const pct = (v: any, digits = 0) =>
  v === null || v === undefined ? "—" : `${(Number(v) * 100).toFixed(digits)}%`;

export default function PlantAnalytics() {
  const [tab, setTab] = useState<Tab>("Overview");
  const [months, setMonths] = useState<string[]>([]);
  const [month, setMonth] = useState("");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const [overview, setOverview] = useState<any>(null);
  const [comparison, setComparison] = useState<any>(null);
  const [delayDamage, setDelayDamage] = useState<any>(null);
  const [workload, setWorkload] = useState<any>(null);
  const [recs, setRecs] = useState<any[]>([]);

  // Load the list of months that actually have plant logs.
  useEffect(() => {
    api.get("/analytics/months")
      .then((r) => {
        const list: string[] = r.data.months || [];
        setMonths(list);
        setMonth(list[0] || r.data.current);
      })
      .catch(() => setLoading(false));
  }, []);

  const loadAll = useCallback(async (m: string) => {
    if (!m) return;
    setLoading(true);
    try {
      const [ov, kc, dd, wl, rc] = await Promise.all([
        api.get(`/analytics/overview?month=${m}`),
        api.get(`/analytics/kpi-comparison?month=${m}`),
        api.get(`/analytics/delay-damage?month=${m}`),
        api.get(`/analytics/workload?month=${m}`),
        api.get(`/analytics/recommendations?month=${m}`),
      ]);
      setOverview(ov.data);
      setComparison(kc.data);
      setDelayDamage(dd.data);
      setWorkload(wl.data);
      setRecs(rc.data.recommendations || []);
    } catch (err) {
      console.error("Failed to load analytics", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (month) loadAll(month); }, [month, loadAll]);

  const runAnalysis = async () => {
    setRunning(true);
    try {
      const res = await api.post("/analytics/analyze", { month });
      const d = res.data;
      Swal.fire({
        icon: "success",
        title: "Analysis complete",
        text: `${d.analysed.length} plant(s) analysed for ${month}` +
              (d.skipped.length ? ` · ${d.skipped.length} skipped (no logs)` : "") +
              (d.failed.length ? ` · ${d.failed.length} failed` : ""),
      });
      await loadAll(month);
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Analysis failed." });
    } finally {
      setRunning(false);
    }
  };

  const ranking = overview?.ranking || [];
  const kpis = overview?.kpis;

  return (
    <div className="space-y-6 text-slate-900">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center">
            <Activity className="w-6 h-6 mr-2 text-indigo-600" /> Plant Performance Analytics
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            Component 4 — production analysis &amp; resource optimization across all plants.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-950"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          >
            {months.length === 0 && <option value="">No data</option>}
            {months.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <Button variant="outline" onClick={runAnalysis} disabled={running || !month}>
            <RefreshCw className={`w-4 h-4 mr-1 ${running ? "animate-spin" : ""}`} />
            {running ? "Analysing..." : "Run Analysis"}
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center text-slate-500">Loading analytics…</div>
      ) : !overview?.analysed ? (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
          <p className="text-slate-600 font-medium">No analysis for {month} yet.</p>
          <p className="text-sm text-slate-500 mt-1">Click <strong>Run Analysis</strong> to score every plant from its daily logs.</p>
        </div>
      ) : (
        <>
          {/* ── Overview ── */}
          {tab === "Overview" && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                <KpiCard icon={<Star className="w-5 h-5" />} tone="indigo" label="Avg Performance"
                  value={kpis.avg_performance_score?.toFixed(2)} sub="out of 5.00" />
                <KpiCard icon={<Trophy className="w-5 h-5" />} tone="amber" label="Best Plant"
                  value={kpis.best_plant?.plant_name} sub={`${kpis.best_plant?.score?.toFixed(2)} / 5`} small />
                <KpiCard icon={<Clock className="w-5 h-5" />} tone="emerald" label="Avg On-Time"
                  value={pct(kpis.avg_on_time_rate, 1)} sub="orders on schedule" />
                <KpiCard icon={<AlertTriangle className="w-5 h-5" />} tone={kpis.avg_damage_rate > 3 ? "red" : "blue"}
                  label="Avg Damage" value={`${kpis.avg_damage_rate}%`} sub="limit 3.0%" />
                <KpiCard icon={<Zap className="w-5 h-5" />} tone="violet" label="Urgent Orders"
                  value={kpis.total_urgent_orders} sub={`${kpis.plants_analysed} plants`} />
              </div>

              {/* Ranking table */}
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
                  <h3 className="font-semibold text-slate-800">Plant Performance Ranking</h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="text-xs uppercase text-slate-500 bg-slate-50 border-b border-slate-200">
                      <tr>
                        <th className="px-4 py-3">Rank</th>
                        <th className="px-4 py-3">Plant</th>
                        <th className="px-4 py-3 text-right">Score</th>
                        <th className="px-4 py-3 text-right">On-Time</th>
                        <th className="px-4 py-3 text-right">Efficiency</th>
                        <th className="px-4 py-3 text-right">Utilization</th>
                        <th className="px-4 py-3 text-right">Damage %</th>
                        <th className="px-4 py-3">Quality</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {ranking.map((r: any) => (
                        <tr key={r.plant_id} className={r.rank === 1 ? "bg-emerald-50/40" : "hover:bg-slate-50/60"}>
                          <td className="px-4 py-3">
                            <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold ${
                              r.rank === 1 ? "bg-indigo-600 text-white" : "bg-slate-200 text-slate-700"}`}>{r.rank}</span>
                          </td>
                          <td className="px-4 py-3">
                            <p className="font-semibold text-slate-900">{r.plant_name}</p>
                            <p className="text-xs text-slate-500">{r.location}</p>
                          </td>
                          <td className="px-4 py-3 text-right">
                            <span className="font-bold text-slate-900">{r.overall_score?.toFixed(2)}</span>
                            <span className="ml-1 text-amber-500">{"★".repeat(r.star_rating_num || 0)}</span>
                          </td>
                          <td className="px-4 py-3 text-right text-slate-700">{pct(r.on_time_rate, 0)}</td>
                          <td className="px-4 py-3 text-right text-slate-700">{pct(r.efficiency, 0)}</td>
                          <td className="px-4 py-3 text-right text-slate-700">{pct(r.utilization, 0)}</td>
                          <td className="px-4 py-3 text-right font-medium">{r.damage_rate?.toFixed(2)}%</td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${BAND_STYLE[r.damage_band]}`}>
                              {r.damage_band}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Score chart */}
              <ChartCard title="Overall Score by Plant" icon={<BarChart3 className="w-4 h-4 text-indigo-600" />}>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={ranking.map((r: any) => ({ name: r.plant_name, score: r.overall_score }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#64748b" }} interval={0} angle={-12} textAnchor="end" height={60} />
                    <YAxis domain={[0, 5]} tick={{ fontSize: 11, fill: "#64748b" }} />
                    <Tooltip contentStyle={{ borderRadius: '8px', color: '#0f172a' }} itemStyle={{ color: '#0f172a' }} />
                    <Bar dataKey="score" fill="#4f46e5" radius={[4, 4, 0, 0]} name="Score" />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>
          )}

          {/* ── KPI Comparison ── */}
          {tab === "KPI Comparison" && comparison && (
            <div className="space-y-6">
              <ChartCard title="Efficiency · Utilization · On-Time" icon={<Gauge className="w-4 h-4 text-indigo-600" />}>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={comparison.plants.map((p: any) => ({
                    name: p.plant_name,
                    Efficiency: Math.round((p.efficiency || 0) * 100),
                    Utilization: Math.round((p.utilization || 0) * 100),
                    "On-Time": Math.round((p.on_time_rate || 0) * 100),
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#64748b" }} interval={0} angle={-12} textAnchor="end" height={60} />
                    <YAxis unit="%" tick={{ fontSize: 11, fill: "#64748b" }} />
                    <Tooltip contentStyle={{ borderRadius: '8px', color: '#0f172a' }} itemStyle={{ color: '#0f172a' }} />
                    <Legend />
                    <Bar dataKey="Efficiency" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Utilization" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="On-Time" fill="#10b981" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="Daily Output Commitment" icon={<TrendingUp className="w-4 h-4 text-indigo-600" />}>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={comparison.plants.map((p: any) => ({ name: p.plant_name, pcs: p.daily_commitment }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#64748b" }} interval={0} angle={-12} textAnchor="end" height={60} />
                    <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
                    <Tooltip contentStyle={{ borderRadius: '8px', color: '#0f172a' }} itemStyle={{ color: '#0f172a' }} />
                    <Bar dataKey="pcs" fill="#8b5cf6" radius={[4, 4, 0, 0]} name="pcs/day" />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>

              {/* Full KPI matrix */}
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
                  <h3 className="font-semibold text-slate-800">Full KPI Matrix</h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="text-xs uppercase text-slate-500 bg-slate-50 border-b border-slate-200">
                      <tr>
                        <th className="px-4 py-3">Plant</th>
                        <th className="px-4 py-3 text-right">Quality</th>
                        <th className="px-4 py-3 text-right">On-Time</th>
                        <th className="px-4 py-3 text-right">Efficiency</th>
                        <th className="px-4 py-3 text-right">Utilization</th>
                        <th className="px-4 py-3 text-right">Damage %</th>
                        <th className="px-4 py-3 text-right">Delay</th>
                        <th className="px-4 py-3 text-right">Daily Pcs</th>
                        <th className="px-4 py-3 text-right">Workload</th>
                        <th className="px-4 py-3 text-right">Urgent</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {comparison.plants.map((p: any) => (
                        <tr key={p.plant_id} className="hover:bg-slate-50/60">
                          <td className="px-4 py-3 font-medium text-slate-900">{p.plant_name}</td>
                          <td className="px-4 py-3 text-right">{p.quality_rating}</td>
                          <td className="px-4 py-3 text-right">{pct(p.on_time_rate)}</td>
                          <td className="px-4 py-3 text-right">{pct(p.efficiency)}</td>
                          <td className="px-4 py-3 text-right">{pct(p.utilization)}</td>
                          <td className="px-4 py-3 text-right">{p.damage_rate?.toFixed(2)}%</td>
                          <td className="px-4 py-3 text-right">{pct(p.delay_ratio)}</td>
                          <td className="px-4 py-3 text-right">{Math.round(p.daily_commitment || 0).toLocaleString()}</td>
                          <td className="px-4 py-3 text-right">{p.total_workload?.toLocaleString()}</td>
                          <td className="px-4 py-3 text-right">{p.urgent_handled}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ── Delay & Damage ── */}
          {tab === "Delay & Damage" && delayDamage && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <KpiCard icon={<AlertTriangle className="w-5 h-5" />} tone={delayDamage.breaching_count ? "red" : "emerald"}
                  label="Above 3% Limit" value={delayDamage.breaching_count} sub={`of ${delayDamage.items.length} plants`} />
                <KpiCard icon={<AlertTriangle className="w-5 h-5" />} tone="amber" label="Worst Damage"
                  value={`${delayDamage.worst_damage?.damage_rate?.toFixed(2)}%`} sub={delayDamage.worst_damage?.plant_name} small />
                <KpiCard icon={<Clock className="w-5 h-5" />} tone="blue" label="Worst Delay"
                  value={pct(delayDamage.worst_delay?.delay_ratio)} sub={delayDamage.worst_delay?.plant_name} small />
              </div>

              <ChartCard title="Damage % vs 3% Acceptable Limit" icon={<AlertTriangle className="w-4 h-4 text-red-500" />}>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={delayDamage.items.map((i: any) => ({ name: i.plant_name, damage: i.damage_rate }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#64748b" }} interval={0} angle={-12} textAnchor="end" height={60} />
                    <YAxis unit="%" tick={{ fontSize: 11, fill: "#64748b" }} />
                    <Tooltip contentStyle={{ borderRadius: '8px', color: '#0f172a' }} itemStyle={{ color: '#0f172a' }} />
                    <Bar dataKey="damage" radius={[4, 4, 0, 0]} name="Damage %">
                      {delayDamage.items.map((i: any, idx: number) => (
                        <Cell key={idx} fill={i.within_limit ? "#10b981" : "#ef4444"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <p className="text-xs text-slate-500 mt-2">
                  Green = within the 3% acceptable limit · Red = needs improvement.
                </p>
              </ChartCard>

              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
                  <h3 className="font-semibold text-slate-800">Delay &amp; Damage Detail</h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="text-xs uppercase text-slate-500 bg-slate-50 border-b border-slate-200">
                      <tr>
                        <th className="px-4 py-3">Plant</th>
                        <th className="px-4 py-3 text-right">Output</th>
                        <th className="px-4 py-3 text-right">Damaged</th>
                        <th className="px-4 py-3 text-right">Damage %</th>
                        <th className="px-4 py-3">Evaluation</th>
                        <th className="px-4 py-3 text-right">Delay Ratio</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {delayDamage.items.map((i: any) => (
                        <tr key={i.plant_id} className="hover:bg-slate-50/60">
                          <td className="px-4 py-3 font-medium text-slate-900">{i.plant_name}</td>
                          <td className="px-4 py-3 text-right">{i.total_output?.toLocaleString()}</td>
                          <td className="px-4 py-3 text-right">{i.damaged_qty?.toLocaleString()}</td>
                          <td className={`px-4 py-3 text-right font-semibold ${i.within_limit ? "text-emerald-600" : "text-red-600"}`}>
                            {i.damage_rate?.toFixed(2)}%
                          </td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${BAND_STYLE[i.damage_band]}`}>
                              {i.damage_band}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right">{pct(i.delay_ratio)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ── Workload ── */}
          {tab === "Workload" && workload && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <ChartCard title="Workload Distribution" icon={<Gauge className="w-4 h-4 text-indigo-600" />}>
                  <ResponsiveContainer width="100%" height={240}>
                    <PieChart>
                      <Pie
                        data={Object.entries(workload.counts).map(([name, value]) => ({ name, value }))}
                        dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={{ fill: '#475569', fontSize: 12 }}
                      >
                        {Object.keys(workload.counts).map((k) => (
                          <Cell key={k} fill={k === "Overloaded" ? "#ef4444" : k === "Optimal" ? "#10b981" : "#3b82f6"} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ borderRadius: '8px', color: '#0f172a' }} itemStyle={{ color: '#0f172a' }} />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </ChartCard>

                <div className="lg:col-span-2 space-y-3">
                  {workload.items.map((i: any) => (
                    <div key={i.plant_id} className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
                      <div className="flex items-center justify-between gap-3 flex-wrap">
                        <div>
                          <p className="font-semibold text-slate-900">{i.plant_name}</p>
                          <p className="text-xs text-slate-500 mt-0.5">{i.advice}</p>
                        </div>
                        <span className={`px-2.5 py-1 rounded-full text-xs font-semibold border ${STATUS_STYLE[i.status]}`}>
                          {i.status}
                        </span>
                      </div>
                      <div className="mt-3">
                        <div className="flex justify-between text-xs text-slate-500 mb-1">
                          <span>Capacity load</span>
                          <span className="font-medium text-slate-700">{pct(i.load_ratio, 0)}</span>
                        </div>
                        <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              i.status === "Overloaded" ? "bg-red-500" : i.status === "Optimal" ? "bg-emerald-500" : "bg-blue-500"}`}
                            style={{ width: `${Math.min(100, (i.load_ratio || 0) * 100)}%` }}
                          />
                        </div>
                        <p className="text-xs text-slate-400 mt-1.5">
                          Machine utilization {pct(i.utilization, 0)} · {i.total_workload?.toLocaleString()} pcs this month
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── Recommendations ── */}
          {tab === "Recommendations" && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-100 bg-slate-50 flex items-center gap-2">
                <Lightbulb className="w-4 h-4 text-amber-500" />
                <h3 className="font-semibold text-slate-800">Resource Optimization Recommendations</h3>
              </div>
              <div className="p-6 space-y-3">
                {recs.length === 0 ? (
                  <p className="text-sm text-slate-500">No recommendations for this month.</p>
                ) : recs.map((r, i) => (
                  <div key={i} className={`rounded-lg border p-4 flex items-start gap-3 ${PRIORITY_STYLE[r.priority] || PRIORITY_STYLE.low}`}>
                    <Lightbulb className="w-4 h-4 mt-0.5 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{r.message}</p>
                      <p className="text-xs opacity-70 mt-0.5">{r.priority} priority · {r.type.replace(/_/g, " ")}</p>
                    </div>
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

function KpiCard({ icon, label, value, sub, tone, small }: {
  icon: React.ReactNode; label: string; value: any; sub?: string; tone: string; small?: boolean;
}) {
  const tones: Record<string, string> = {
    indigo: "bg-indigo-50 text-indigo-600",
    amber: "bg-amber-50 text-amber-600",
    emerald: "bg-emerald-50 text-emerald-600",
    red: "bg-red-50 text-red-600",
    blue: "bg-blue-50 text-blue-600",
    violet: "bg-violet-50 text-violet-600",
  };
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center mb-3 ${tones[tone] || tones.indigo}`}>
        {icon}
      </div>
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</p>
      <p className={`font-bold text-slate-900 mt-1 ${small ? "text-base leading-snug" : "text-2xl"}`}>{value ?? "—"}</p>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function ChartCard({ title, icon, children }: { title: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 text-slate-900">
      <h3 className="font-semibold text-slate-800 mb-4 flex items-center gap-2">{icon}{title}</h3>
      {children}
    </div>
  );
}
