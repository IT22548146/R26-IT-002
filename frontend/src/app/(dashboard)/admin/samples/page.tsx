"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ClipboardList, Search, Download, Mail, Clock, Eye } from "lucide-react";
import OrderTracker from "@/components/OrderTracker";

const actionPill = (a?: string) =>
  a === "Approved" ? "bg-green-100 text-green-700"
    : a === "Rejected" ? "bg-orange-100 text-orange-700"
    : "bg-slate-100 text-slate-600";

const fmtDateTime = (s?: string) => {
  if (!s) return "";
  const d = new Date(s);
  return isNaN(d.getTime()) ? String(s) : d.toLocaleString();
};

export default function AdminSampleOrders() {
  const router = useRouter();
  const [orders, setOrders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [polling, setPolling] = useState(false);

  const fetchOrders = async () => {
    try {
      const res = await api.get("/admin/orders/sample");
      setOrders(res.data);
    } catch (err) {
      console.error("Failed to fetch sample orders", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders();
  }, []);

  const handleDownloadPdf = async (orderId: number, styleNumber: string) => {
    try {
      const res = await api.get(`/admin/orders/sample/${orderId}/pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `${styleNumber}_style.pdf`;
      a.click();
      setTimeout(() => window.URL.revokeObjectURL(url), 10_000);
    } catch (err: any) {
      Swal.fire({ icon: 'error', title: 'Error', text: "Failed to download the style PDF." });
    }
  };

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

  if (loading) return <div>Loading...</div>;

  const filteredOrders = orders.filter((o) =>
    (o.style_number || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
    (o.buyer_name || "").toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <ClipboardList className="w-6 h-6 mr-2 text-blue-600" />
          Sample Orders Management
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

      {filteredOrders.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
          <p className="text-slate-500">No sample orders found.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {filteredOrders.map((order) => {
            // Awaiting-reply badge is the only derived state the overview card needs.
            return (
              <div key={order.id} className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden transition-all duration-200 hover:shadow-md">
                
                {/* Header Section */}
                <div className="p-6 border-b border-slate-100 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                  <div>
                    <div className="flex items-center space-x-3 mb-2">
                      <span className="text-lg font-extrabold text-slate-900 tracking-tight">Style: {order.style_number}</span>
                      <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                        order.status === 'Pending' ? 'bg-amber-50 text-amber-700 border-amber-200' :
                        order.status === 'Processing' ? 'bg-blue-50 text-blue-700 border-blue-200' :
                        order.status === 'Completed' ? 'bg-green-50 text-green-700 border-green-200' :
                        'bg-slate-50 text-slate-700 border-slate-200'
                      }`}>
                        {order.status}
                      </span>
                      {order.feasibility && (
                        <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                          order.feasibility === 'Feasible'
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : 'bg-red-50 text-red-700 border-red-200'
                        }`}>
                          {order.feasibility}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-slate-600 flex flex-wrap items-center gap-x-4 gap-y-2">
                      <span>Buyer: <strong className="text-slate-800">{order.buyer_name}</strong></span>
                      <span className="text-slate-300">|</span>
                      <span>Qty: <strong className="text-slate-800">{order.sample_qty}</strong></span>
                      <span className="text-slate-300">|</span>
                      <span>Target: <strong className="text-slate-800">{new Date(order.receive_date).toLocaleDateString()}</strong></span>
                    </p>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap justify-end">
                    {order.style_pdf_path && (
                      <Button variant="outline" onClick={() => handleDownloadPdf(order.id, order.style_number)}>
                        <Download className="w-4 h-4 mr-1" /> Style PDF
                      </Button>
                    )}
                    {order.status === "Pending" && Boolean(order.timeline_email_sent_at) && !order.customer_response && (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-purple-50 text-purple-700 border border-purple-200">
                        <Clock className="w-3.5 h-3.5" /> Awaiting customer reply
                      </span>
                    )}
                    <Button variant="ghost" onClick={() => router.push(`/admin/samples/${order.id}`)}>
                      <Eye className="w-4 h-4 mr-1" /> View Full Details
                    </Button>
                  </div>
                </div>

                {/* Order tracking */}
                <div className="px-6 pb-5">
                  <OrderTracker type="sample" order={order} tone="blue" />
                </div>
              </div>
            );
          })}
        </div>
      )}

    </div>
  );
}

