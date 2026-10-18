"use client";

import { useState, useEffect } from "react";
import api from "@/lib/api";
import { ClipboardList, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import Swal from "@/lib/swal";
import OrderTracker, { StageSelect } from "@/components/OrderTracker";
import { getApiErrorMessage } from "@/lib/errors";

interface PlantSampleOrder {
  id: number;
  style_number: string;
  status: string;
  production_stage?: string | null;
  buyer_name: string;
  sample_qty?: number;
  receive_date?: string;
  buyer_required_date?: string;
  buyer_priority_rank?: number;
  planned_shipment_date?: string;
  estimated_completion_date?: string;
  comments?: string | null;
}

export default function PlantSampleOrders() {
  const [orders, setOrders] = useState<PlantSampleOrder[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchOrders = async () => {
    try {
      const res = await api.get("/plant/sample-orders");
      setOrders(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleMarkReady = async (orderId: number) => {
    const result = await Swal.fire({
      title: "Confirm",
      text: "Are you sure this sample order is 100% complete and ready?",
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#3085d6',
      cancelButtonColor: '#d33',
      confirmButtonText: 'Yes, mark it ready'
    });
    if (!result.isConfirmed) return;
    try {
      await api.post(`/plant/sample-orders/${orderId}/ready`);
      Swal.fire({ icon: 'success', title: "Success", text: "Sample order marked as completed!" });
      fetchOrders();
    } catch (err: unknown) {
      Swal.fire({ icon: 'error', title: 'Error', text: getApiErrorMessage(err, "Failed to mark ready.") });
    }
  };

  const handleStageChange = async (orderId: number, stage: string) => {
    try {
      await api.post(`/plant/sample-orders/${orderId}/stage`, { stage });
      Swal.fire({ icon: "success", title: `Stage updated to ${stage}` });
      fetchOrders();
    } catch (err: unknown) {
      Swal.fire({ icon: "error", title: "Error", text: getApiErrorMessage(err, "Failed to update stage.") });
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void fetchOrders(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <ClipboardList className="w-6 h-6 mr-2 text-indigo-600" />
          Assigned Sample Orders
        </h2>
      </div>

      {loading ? (
        <div className="text-slate-500">Loading...</div>
      ) : orders.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center text-slate-500">
          You currently have no assigned sample orders.
        </div>
      ) : (
        <div className="space-y-4">
          {orders.map((order) => (
            <div key={order.id} className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden p-6">
              <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                  <div className="flex items-center space-x-3 mb-2">
                    <span className="text-lg font-bold text-slate-900">Style: {order.style_number}</span>
                    <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      (order.status === 'Processing' || order.status === 'Assigned') ? 'bg-blue-100 text-blue-800' :
                      order.status === 'Completed' ? 'bg-green-100 text-green-800' :
                      'bg-slate-100 text-slate-800'
                    }`}>
                      {order.status}
                    </span>
                    {order.buyer_priority_rank && (
                      <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-0.5 text-xs font-bold text-indigo-700">
                        Buyer priority #{order.buyer_priority_rank}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-slate-500">
                    Buyer: {order.buyer_name} | Qty: <span className="font-semibold text-slate-700">{order.sample_qty}</span>
                    {" | "}Required: {order.buyer_required_date}
                    {order.planned_shipment_date && <> | Planned shipment: <strong>{order.planned_shipment_date}</strong></>}
                  </p>
                  {order.comments && (
                    <p className="text-sm text-slate-500 mt-2 italic border-l-2 border-indigo-200 pl-3">
                      &ldquo;{order.comments}&rdquo;
                    </p>
                  )}
                </div>
                {(order.status === "Processing" || order.status === "Assigned") && (
                  <Button onClick={() => handleMarkReady(order.id)} className="bg-green-600 hover:bg-green-700 text-white border-0 shrink-0">
                    <CheckCircle className="w-4 h-4 mr-2" /> Mark Ready
                  </Button>
                )}
              </div>

              {/* Production tracking + stage control */}
              <div className="mt-5 pt-5 border-t border-slate-100">
                <OrderTracker type="sample" order={order} tone="blue" />
                {(order.status === "Processing" || order.status === "Assigned") && (
                  <div className="mt-5 flex justify-end">
                    <StageSelect value={order.production_stage ?? "Pending"} onChange={(s) => handleStageChange(order.id, s)} />
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
