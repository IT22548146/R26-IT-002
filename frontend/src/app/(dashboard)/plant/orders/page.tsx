"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Package, FileEdit, CheckCircle, AlertTriangle } from "lucide-react";
import OrderTracker, { StageSelect } from "@/components/OrderTracker";

export default function PlantOrders() {
  const [orders, setOrders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeLogForm, setActiveLogForm] = useState<number | null>(null);
  const [submittingLog, setSubmittingLog] = useState(false);

  // Production date defaults to today but is editable, so a missed day can still be logged.
  const todayStr = new Date().toISOString().slice(0, 10);
  const [logData, setLogData] = useState({
    log_date: new Date().toISOString().slice(0, 10),
    plant_daily_output: "",
    daily_damage_qty: "",
    max_daily_damage_qty: "",
    machine_breakdown_count: "",
    worker_shortage_count: "",
    cumulative_completed_qty: ""
  });

  const fetchOrders = async () => {
    try {
      const res = await api.get("/plant/orders");
      setOrders(res.data);
    } catch (err) {
      console.error("Failed to fetch assigned orders", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders();
  }, []);

  const handleSubmitLog = async (e: React.FormEvent, orderId: number) => {
    e.preventDefault();
    setSubmittingLog(true);
    try {
      const payload = {
        log_date: logData.log_date,
        plant_daily_output: Number(logData.plant_daily_output),
        daily_damage_qty: Number(logData.daily_damage_qty),
        max_daily_damage_qty: Number(logData.max_daily_damage_qty),
        machine_breakdown_count: Number(logData.machine_breakdown_count),
        worker_shortage_count: Number(logData.worker_shortage_count),
        cumulative_completed_qty: Number(logData.cumulative_completed_qty)
      };
      
      const res = await api.post(`/plant/orders/${orderId}/log`, payload);
      
      // If AI detected a critical issue, warn them immediately on screen
      if (res.data.c3_result?.severity_class === "Critical") {
         Swal.fire({ icon: 'warning', title: `⚠️ CRITICAL AI ALERT ⚠️\n\nRisk: ${res.data.c3_result.risk_type_class}\nAction Required! An email has also been sent to Admin.` });
      } else {
         Swal.fire({ icon: 'success', title: `Log submitted successfully! AI Status: ${res.data.c3_result?.severity_class || 'Model offline / No risk'}` });
      }

      setActiveLogForm(null);
      setLogData({
        log_date: new Date().toISOString().slice(0, 10),
        plant_daily_output: "", daily_damage_qty: "", max_daily_damage_qty: "",
        machine_breakdown_count: "", worker_shortage_count: "", cumulative_completed_qty: ""
      });
      fetchOrders();
    } catch (err: any) {
      Swal.fire({ icon: 'error', title: 'Error', text: err.response?.data?.error || "Failed to submit log." });
    } finally {
      setSubmittingLog(false);
    }
  };

  const handleStageChange = async (orderId: number, stage: string) => {
    try {
      await api.post(`/plant/orders/${orderId}/stage`, { stage });
      Swal.fire({ icon: "success", title: `Stage updated to ${stage}` });
      fetchOrders();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to update stage." });
    }
  };

  const handleApprove = async (orderId: number) => {
    try {
      await api.post(`/plant/orders/${orderId}/approve`);
      Swal.fire({ icon: 'success', title: "Assignment approved — production started." });
      fetchOrders();
    } catch (err: any) {
      Swal.fire({ icon: 'error', title: 'Error', text: err.response?.data?.error || "Failed to approve." });
    }
  };

  const handleMarkReady = async (orderId: number) => {
    const result = await Swal.fire({ title: "Confirm", text: "Are you sure this order is 100% complete and ready for shipment?", icon: 'warning', showCancelButton: true, confirmButtonColor: '#3085d6', cancelButtonColor: '#d33', confirmButtonText: 'Yes' });
    if (!result.isConfirmed) return;
    try {
      await api.post(`/plant/orders/${orderId}/ready`);
      Swal.fire({ icon: 'info', title: "Order marked complete! Buyer and Admin have been notified." });
      fetchOrders();
    } catch (err: any) {
      Swal.fire({ icon: 'error', title: 'Error', text: err.response?.data?.error || "Failed to mark complete." });
    }
  };

  // Status dropdown handler (replaces the single Mark-Complete button).
  const handleStatusChange = (order: any, value: string) => {
    if (value === "Completed") handleMarkReady(order.id);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <Package className="w-6 h-6 mr-2 text-purple-600" />
          Assigned Production
        </h2>
      </div>

      {loading ? (
        <div>Loading...</div>
      ) : orders.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
          <p className="text-slate-500">You currently have no assigned orders.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {orders.map((order) => (
            <div key={order.id} className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
              <div className="p-6 border-b border-slate-100 flex justify-between items-start">
                <div>
                  <div className="flex items-center space-x-3 mb-2">
                    <span className="text-lg font-bold text-slate-900">Style: {order.style_number}</span>
                    <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      order.status === 'Processing' ? 'bg-blue-100 text-blue-800' :
                      order.status === 'Completed' ? 'bg-green-100 text-green-800' :
                      order.status === 'Shipped' ? 'bg-slate-100 text-slate-600' :
                      'bg-slate-100 text-slate-800'
                    }`}>
                      {order.status}
                    </span>
                  </div>
                  <p className="text-sm text-slate-500">
                    Buyer: {order.buyer_name} | Qty Allocated: <span className="font-semibold text-slate-700">{order.allocated_qty}</span> | Required Date: {order.buyer_required_date}
                  </p>
                </div>
                
                {order.status === "Processing" && (
                  !order.plant_approved_at ? (
                    <div className="flex flex-col items-end gap-1">
                      <Button onClick={() => handleApprove(order.id)} className="bg-purple-600 hover:bg-purple-700 text-white border-0">
                        <CheckCircle className="w-4 h-4 mr-2" /> Approve Assignment
                      </Button>
                      <span className="text-xs text-slate-400">Accept to start production</span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      {order.expected_completion_date && (
                        <span className="text-xs text-slate-500 mr-1">
                          Est. completion: <strong className="text-slate-700">{order.expected_completion_date}</strong>
                        </span>
                      )}
                      <Button variant="outline" onClick={() => setActiveLogForm(activeLogForm === order.id ? null : order.id)}>
                        <FileEdit className="w-4 h-4 mr-2" /> Log Daily Data
                      </Button>
                      <select
                        defaultValue=""
                        onChange={(e) => handleStatusChange(order, e.target.value)}
                        className="h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-950"
                      >
                        <option value="" disabled>Update status…</option>
                        <option value="Processing">In Production</option>
                        <option value="Completed">Mark Completed</option>
                      </select>
                    </div>
                  )
                )}
              </div>

              {/* Production tracking + stage control */}
              <div className="px-6 py-5 border-b border-slate-100">
                <OrderTracker type="bulk" order={order} tone="indigo" />
                {order.status === "Processing" && order.plant_approved_at && (
                  <div className="mt-5 flex justify-end">
                    <StageSelect value={order.production_stage} onChange={(s) => handleStageChange(order.id, s)} />
                  </div>
                )}
              </div>

              {/* Daily Log Form */}
              {activeLogForm === order.id && (
                <div className="bg-slate-50 p-6 border-b border-slate-100">
                  <h4 className="text-sm font-semibold text-slate-700 mb-3 flex items-center">
                    <AlertTriangle className="w-4 h-4 mr-2 text-amber-500" />
                    Submit Daily Production (Runs AI Component 3)
                  </h4>
                  <form onSubmit={(e) => handleSubmitLog(e, order.id)} className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1">Production Date</label>
                        <Input type="date" required max={todayStr} value={logData.log_date}
                               onChange={e => setLogData({...logData, log_date: e.target.value})} />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1">Output</label>
                        <Input type="number" required value={logData.plant_daily_output} onChange={e => setLogData({...logData, plant_daily_output: e.target.value})} placeholder="e.g. 400" />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1">Cumulative Completed</label>
                        <Input type="number" required value={logData.cumulative_completed_qty} onChange={e => setLogData({...logData, cumulative_completed_qty: e.target.value})} placeholder="e.g. 1200" />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1">Daily Damage Qty</label>
                        <Input type="number" required value={logData.daily_damage_qty} onChange={e => setLogData({...logData, daily_damage_qty: e.target.value})} placeholder="e.g. 5" />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1">Max Tolerated Damage</label>
                        <Input type="number" required value={logData.max_daily_damage_qty} onChange={e => setLogData({...logData, max_daily_damage_qty: e.target.value})} placeholder="e.g. 15" />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1">Machine Breakdowns</label>
                        <Input type="number" required value={logData.machine_breakdown_count} onChange={e => setLogData({...logData, machine_breakdown_count: e.target.value})} placeholder="e.g. 0" />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1">Worker Shortages</label>
                        <Input type="number" required value={logData.worker_shortage_count} onChange={e => setLogData({...logData, worker_shortage_count: e.target.value})} placeholder="e.g. 0" />
                      </div>
                    </div>
                    <div className="flex justify-end">
                      <Button type="submit" disabled={submittingLog}>
                        {submittingLog ? "Submitting..." : "Submit Log & Run AI Scan"}
                      </Button>
                    </div>
                  </form>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
