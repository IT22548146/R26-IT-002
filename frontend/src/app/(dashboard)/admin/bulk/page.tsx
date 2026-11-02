"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Package, Eye, Mail, Download, Search, AlertTriangle } from "lucide-react";
import OrderTracker from "@/components/OrderTracker";

const TABS = ["All", "Pending", "CustomerPending", "Processing", "Hold", "Completed", "Shipped"];
const TAB_LABEL: Record<string, string> = {
  All: "All", Pending: "Pending", CustomerPending: "Cust. Req Pending",
  Processing: "Processing", Hold: "On Hold", Completed: "Completed", Shipped: "Shipped",
};

const statusPill = (status: string) => ({
  Pending: "bg-amber-100 text-amber-800",
  CustomerPending: "bg-purple-100 text-purple-800",
  Processing: "bg-blue-100 text-blue-800",
  Hold: "bg-orange-100 text-orange-800",
  Completed: "bg-green-100 text-green-800",
  Shipped: "bg-slate-200 text-slate-600",
}[status] || "bg-slate-100 text-slate-800");

export default function AdminBulkOrders() {
  const router = useRouter();
  const [orders, setOrders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [polling, setPolling] = useState(false);

  const fetchOrders = async () => {
    try {
      const res = await api.get("/admin/orders/bulk");
      setOrders(res.data);
    } catch (err) {
      console.error("Failed to fetch bulk orders", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchOrders(); }, []);

  // A c2_result is only usable if the prediction actually succeeded. A failed
  // Component-2 run is stored as { error: "..." } (truthy but has no timeline or
  // plant ranking) — treat that, and any result missing production_days, as "no AI data".
  const c2Ready = (order: any) => {
    const c2 = order.c2_result;
    return Boolean(c2 && !c2.error && c2.production_days);
  };

  const baseFiltered = tab === "All" ? orders : orders.filter((o) => o.status === tab);
  const filtered = baseFiltered.filter((o) =>
    (o.style_number || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
    (o.buyer_name || "").toLowerCase().includes(searchQuery.toLowerCase())
  );
  const countFor = (t: string) => (t === "All" ? orders.length : orders.filter((o) => o.status === t).length);

  const handlePollInbox = async () => {
    setPolling(true);
    try {
      const res = await api.post("/admin/inbound-email/poll");
      const d = res.data;
      if (d.configured === false) {
        Swal.fire({ icon: "info", title: "Email checking not set up", text: d.message });
      } else if (d.error) {
        Swal.fire({ icon: "error", title: "Inbox error", text: d.error });
      } else {
        Swal.fire({ icon: "success", title: "Inbox checked", text: `${d.fetched} new email(s), ${d.applied} applied to orders.` });
        if (d.applied) fetchOrders();
      }
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || err.response?.data?.message || "Failed to check inbox." });
    } finally {
      setPolling(false);
    }
  };

  const handleDownloadPdf = async (orderId: number, styleNumber: string) => {
    try {
      const res = await api.get(`/admin/orders/bulk/${orderId}/pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `${styleNumber}_style.pdf`; a.click();
      setTimeout(() => window.URL.revokeObjectURL(url), 10_000);
    } catch {
      Swal.fire({ icon: "error", title: "Error", text: "Failed to download the style PDF." });
    }
  };

  if (loading) return <div>Loading...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <Package className="w-6 h-6 mr-2 text-indigo-600" /> Bulk Orders Management
        </h2>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handlePollInbox} disabled={polling}>
            <Mail className="w-4 h-4 mr-1" /> {polling ? "Checking..." : "Check Email Replies"}
          </Button>
          <div className="relative w-full max-w-xs">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Search className="h-4 w-4 text-slate-400" />
            </div>
            <Input
              type="text"
              placeholder="Search by style or buyer..."
              className="pl-10 shadow-sm"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* Status tabs */}
      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {TAB_LABEL[t]} <span className="text-xs text-slate-400">({countFor(t)})</span>
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
          <p className="text-slate-500">No orders in this view.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map((order) => {
            const c2 = order.c2_result;
            const c2ok = c2Ready(order);
            const c2Broken = Boolean(c2) && !c2ok; // stored result exists but is unusable
            return (
              <div key={order.id} className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                {/* Condensed header */}
                <div className="p-5 flex flex-wrap justify-between items-start gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center space-x-3 mb-1">
                      <span className="text-lg font-bold text-slate-900">Style: {order.style_number}</span>
                      <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${statusPill(order.status)}`}>
                        {TAB_LABEL[order.status] || order.status}
                      </span>
                      {c2Broken && (
                        <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 inline-flex items-center gap-1" title={order.c2_result?.error || "The AI feasibility run did not complete for this order."}>
                          <AlertTriangle className="w-3 h-3" /> AI analysis unavailable
                        </span>
                      )}
                      {order.customer_response && (
                        <span className="text-xs text-slate-400">Customer: {order.customer_response}</span>
                      )}
                    </div>
                    <p className="text-sm text-slate-500">
                      Buyer: <strong className="text-slate-700">{order.buyer_name}</strong> ·
                      Qty: <strong className="text-slate-700">{order.bulk_order_quantity?.toLocaleString()}</strong> ·
                      Required: <strong className="text-slate-700">{order.buyer_required_date}</strong>
                    </p>
                    {order.customer_response && (order.extension_days_requested || order.customer_message) && (
                      <div className="mt-2 inline-flex items-start gap-2 rounded-lg border border-purple-200 bg-purple-50 px-3 py-1.5 text-xs text-purple-800">
                        <span className="font-semibold">Customer reply:</span>
                        <span>
                          {order.customer_response === "Approved" ? "Approved" : "Requested changes"}
                          {order.extension_days_requested ? ` · +${order.extension_days_requested} day(s) requested` : ""}
                          {order.customer_message ? ` · "${order.customer_message}"` : ""}
                        </span>
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {order.style_pdf_path && (
                      <Button variant="outline" size="sm" onClick={() => handleDownloadPdf(order.id, order.style_number)}>
                        <Download className="w-4 h-4 mr-1" /> Style PDF
                      </Button>
                    )}
                    <Button variant="ghost" onClick={() => router.push(`/admin/bulk/${order.id}`)}>
                      <Eye className="w-4 h-4 mr-1" /> View Full Details
                    </Button>
                  </div>
                </div>

                {/* Order tracking */}
                <div className="px-5 pb-4">
                  <OrderTracker type="bulk" order={order} tone="indigo" />
                </div>

              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
