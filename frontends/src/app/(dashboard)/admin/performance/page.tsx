"use client";
import Swal from "@/lib/swal";

import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { Button } from "@/components/ui/Button";
import { Activity, Star, Factory, TrendingUp } from "lucide-react";

interface PerformanceRecommendation {
  action: string;
  probability?: number;
}

interface Component4Result {
  star_rating?: string;
  star_rating_num?: number;
  performance_score?: number;
  overall_priority?: string;
  recommendations?: PerformanceRecommendation[];
}

interface CompletedOrder {
  id: number;
  plant_id: string;
  style_number: string;
  status: string;
  buyer_name: string;
  plant_name?: string | null;
  plant_location?: string | null;
  allocated_qty?: number | null;
  bulk_order_quantity?: number | null;
  log_count: number;
  c4_result?: Component4Result | null;
}

const rowKey = (orderId: number, plantId: string) => `${orderId}:${plantId}`;

export default function AdminPerformance() {
  const [orders, setOrders] = useState<CompletedOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, Component4Result>>({});

  const fetchOrders = useCallback(async () => {
    try {
      const res = await api.get("/admin/performance");
      setOrders(res.data);
      // Seed with any previously-stored results.
      const fetchedOrders = res.data as CompletedOrder[];
      const seeded: Record<string, Component4Result> = {};
      fetchedOrders.forEach((order) => {
        if (order.c4_result) seeded[rowKey(order.id, order.plant_id)] = order.c4_result;
      });
      setResults(seeded);
    } catch (err) {
      console.error("Failed to fetch performance data", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void fetchOrders(), 0);
    return () => window.clearTimeout(timer);
  }, [fetchOrders]);

  const runAnalysis = async (orderId: number, plantId: string) => {
    const key = rowKey(orderId, plantId);
    setRunning(key);
    try {
      const res = await api.get(`/admin/orders/bulk/${orderId}/analysis`, {
        params: { plant_id: plantId },
      });
      setResults((prev) => ({ ...prev, [key]: res.data.component4_result }));
    } catch (err: unknown) {
      Swal.fire({ icon: "error", title: "Error", text: getApiErrorMessage(err, "Analysis failed. The order needs production logs.") });
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
            const key = rowKey(order.id, order.plant_id);
            const c4 = results[key];
            return (
              <div key={key} className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
                <div className="flex flex-wrap justify-between items-start gap-3">
                  <div>
                    <div className="flex items-center gap-3 mb-1">
                      <span className="text-lg font-bold text-slate-900">Style: {order.style_number}</span>
                      <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">{order.status}</span>
                    </div>
                    <p className="text-sm text-slate-500">
                      Buyer: <strong className="text-slate-700">{order.buyer_name}</strong> ·
                      Plant: <strong className="text-slate-700">{order.plant_name || "—"}</strong> ·
                      Location: <strong className="text-slate-700">{order.plant_location || "—"}</strong> ·
                      Allocated Qty: <strong className="text-slate-700">{(order.allocated_qty ?? order.bulk_order_quantity)?.toLocaleString()}</strong> ·
                      Logs: <strong className="text-slate-700">{order.log_count}</strong>
                    </p>
                  </div>
                  <Button onClick={() => runAnalysis(order.id, order.plant_id)} disabled={running === key || order.log_count === 0}
                    className="bg-fuchsia-600 hover:bg-fuchsia-700">
                    <Activity className="w-4 h-4 mr-1" /> {running === key ? "Analysing..." : c4 ? "Re-run Analysis" : "Run Analysis"}
                  </Button>
                </div>

                {order.log_count === 0 && (
                  <p className="mt-3 text-xs text-amber-600">No production logs — this order cannot be scored.</p>
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
                          {c4.recommendations.map((recommendation, idx) => (
                            <li key={idx} className="text-sm flex items-start gap-2 bg-white border border-slate-200 rounded px-3 py-2">
                              <span className="text-fuchsia-500 mt-0.5">•</span>
                              <span className="text-slate-700">{recommendation.action}
                                {typeof recommendation.probability === "number" && <span className="text-slate-400"> ({(recommendation.probability * 100).toFixed(0)}%)</span>}
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
