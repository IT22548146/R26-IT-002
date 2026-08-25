"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Activity, Star, Factory, TrendingUp } from "lucide-react";

export default function AdminPerformance() {
  const [orders, setOrders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState<number | null>(null);
  const [results, setResults] = useState<Record<number, any>>({});

  const fetchOrders = async () => {
    try {
      const res = await api.get("/admin/performance");
      setOrders(res.data);
      // Seed with any previously-stored results.
      const seeded: Record<number, any> = {};
      res.data.forEach((o: any) => { if (o.c4_result) seeded[o.id] = o.c4_result; });
      setResults(seeded);
    } catch (err) {
      console.error("Failed to fetch performance data", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchOrders(); }, []);

  const runAnalysis = async (orderId: number) => {
    setRunning(orderId);
    try {
      const res = await api.get(`/admin/orders/bulk/${orderId}/analysis`);
      setResults((prev) => ({ ...prev, [orderId]: res.data.component4_result }));
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Analysis failed. The order needs production logs." });
    } finally {
      setRunning(null);
    }
  };

  if (loading) return <div>Loading...</div>;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <Activity className="w-6 h-6 mr-2 text-fuchsia-600" /> Garment Performance Analysis
        </h2>
        <p className="text-sm text-slate-500 mt-1">
          Post-completion performance scoring for delivered orders, independent of the production workflow.
        </p>
      </div>

      {orders.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
          <p className="text-slate-500">No completed orders to analyse yet.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {orders.map((order) => {
            const c4 = results[order.id];
            return (
              <div key={order.id} className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
                <div className="flex flex-wrap justify-between items-start gap-3">
                  <div>
                    <div className="flex items-center gap-3 mb-1">
                      <span className="text-lg font-bold text-slate-900">Style: {order.style_number}</span>
                      <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">{order.status}</span>
                    </div>
                    <p className="text-sm text-slate-500">
                      Buyer: <strong className="text-slate-700">{order.buyer_name}</strong> ·
                      Plant: <strong className="text-slate-700">{order.plant_name || "—"}</strong> ·
                      Qty: <strong className="text-slate-700">{order.bulk_order_quantity?.toLocaleString()}</strong> ·
                      Logs: <strong className="text-slate-700">{order.log_count}</strong>
                    </p>
                  </div>
                  <Button onClick={() => runAnalysis(order.id)} disabled={running === order.id || order.log_count === 0}
                    className="bg-fuchsia-600 hover:bg-fuchsia-700">
                    <Activity className="w-4 h-4 mr-1" /> {running === order.id ? "Analysing..." : c4 ? "Re-run Analysis" : "Run Analysis"}
                  </Button>
                </div>

                {order.log_count === 0 && (
                  <p className="mt-3 text-xs text-amber-600">No production logs — this order can't be scored.</p>
                )}

                {c4 && (
                  <div className="mt-5 border-t border-slate-100 pt-5 grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="bg-slate-50 rounded-lg border border-slate-100 p-4 flex items-center gap-3">
                      <Star className="w-6 h-6 text-amber-500" />
                      <div>
                        <p className="text-xs text-slate-400 uppercase tracking-wide">Star Rating</p>
                        <p className="text-lg font-bold text-slate-800">{c4.star_rating ?? c4.star_rating_num ?? "—"}</p>
                      </div>
                    </div>
                    <div className="bg-slate-50 rounded-lg border border-slate-100 p-4 flex items-center gap-3">
                      <TrendingUp className="w-6 h-6 text-blue-500" />
                      <div>
                        <p className="text-xs text-slate-400 uppercase tracking-wide">Performance Score</p>
                        <p className="text-lg font-bold text-slate-800">{c4.performance_score ?? "—"}</p>
                      </div>
                    </div>
                    <div className="bg-slate-50 rounded-lg border border-slate-100 p-4 flex items-center gap-3">
                      <Factory className="w-6 h-6 text-emerald-500" />
                      <div>
                        <p className="text-xs text-slate-400 uppercase tracking-wide">Overall</p>
                        <p className="text-lg font-bold text-slate-800 capitalize">{c4.overall_priority ?? "—"}</p>
                      </div>
                    </div>

                    <div className="md:col-span-3">
                      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Recommendations</p>
                      {c4.recommendations?.length ? (
                        <ul className="space-y-1.5">
                          {c4.recommendations.map((r: any, idx: number) => (
                            <li key={idx} className="text-sm flex items-start gap-2 bg-white border border-slate-200 rounded px-3 py-2">
                              <span className="text-fuchsia-500 mt-0.5">•</span>
                              <span className="text-slate-700">{r.action}
                                {typeof r.probability === "number" && <span className="text-slate-400"> ({(r.probability * 100).toFixed(0)}%)</span>}
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-sm text-slate-500">No recommendations — performance is on track.</p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
