"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import {
  ClipboardList, Package, ArrowRight, Clock, CheckCircle, Bell,
  Plus, Truck, Sparkles, LifeBuoy, ChevronRight,
} from "lucide-react";
import Link from "next/link";
import api from "@/lib/api";

const SAMPLE_PILL: Record<string, string> = {
  Pending: "bg-amber-100 text-amber-700",
  Processing: "bg-blue-100 text-blue-700",
  Completed: "bg-green-100 text-green-700",
  Cancelled: "bg-slate-200 text-slate-600",
};
const BULK_PILL: Record<string, string> = {
  Pending: "bg-amber-100 text-amber-700",
  CustomerPending: "bg-purple-100 text-purple-700",
  Processing: "bg-blue-100 text-blue-700",
  Hold: "bg-orange-100 text-orange-700",
  Completed: "bg-green-100 text-green-700",
  Shipped: "bg-slate-200 text-slate-600",
};
const bulkLabel = (s: string) => (s === "CustomerPending" ? "Awaiting your approval" : s);

export default function BuyerDashboard() {
  const { user } = useAuth();
  const [sampleOrders, setSampleOrders] = useState<any[]>([]);
  const [bulkOrders, setBulkOrders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        const [samplesRes, bulkRes] = await Promise.all([
          api.get("/buyer/orders/sample"),
          api.get("/buyer/orders/bulk"),
        ]);
        setSampleOrders(samplesRes.data);
        setBulkOrders(bulkRes.data);
      } catch (err) {
        console.error("Failed to load dashboard data", err);
      } finally {
        setLoading(false);
      }
    };
    fetchDashboardData();
  }, []);

  const pendingSamples = sampleOrders.filter((o) => o.status === "Pending").length;
  const inProduction = bulkOrders.filter((o) => o.status === "Processing").length;
  const awaitingApproval = bulkOrders.filter((o) => o.status === "CustomerPending").length;
  const shipped = bulkOrders.filter((o) => o.status === "Shipped").length;

  const firstName = (user?.full_name || "").split(" ")[0] || "there";

  const recent = [
    ...bulkOrders.map((o) => ({ ...o, type: "Bulk" as const })),
    ...sampleOrders.map((o) => ({ ...o, type: "Sample" as const })),
  ].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).slice(0, 6);

  const stats = [
    { label: "Pending Samples", value: pendingSamples, icon: ClipboardList, tint: "bg-amber-50 text-amber-600", href: "/buyer/samples" },
    { label: "In Production", value: inProduction, icon: Package, tint: "bg-blue-50 text-blue-600", href: "/buyer/bulk" },
    { label: "Awaiting Your Approval", value: awaitingApproval, icon: Clock, tint: "bg-purple-50 text-purple-600", href: "/buyer/bulk" },
    { label: "Shipped", value: shipped, icon: Truck, tint: "bg-emerald-50 text-emerald-600", href: "/buyer/bulk" },
  ];

  return (
    <div className="space-y-6">
      {/* Welcome hero — bright, customer-friendly */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-blue-600 to-indigo-600 text-white p-8">
        <div className="relative z-10 flex flex-col md:flex-row md:items-center md:justify-between gap-6">
          <div>
            <p className="text-blue-100 text-sm font-medium mb-1 flex items-center gap-1">
              <Sparkles className="w-4 h-4" /> Your production hub
            </p>
            <h2 className="text-3xl font-bold">Hello, {firstName} 👋</h2>
            <p className="text-blue-100 mt-2 max-w-lg">
              Request samples, place bulk orders, and follow every order through to delivery — all in one place.
            </p>
          </div>
          <div className="flex flex-wrap gap-3 shrink-0">
            <Link href="/buyer/samples?new=1" className="inline-flex items-center gap-2 px-5 py-2.5 bg-white text-blue-700 font-semibold rounded-lg hover:bg-blue-50 transition-colors">
              <Plus className="w-4 h-4" /> New Sample
            </Link>
            <Link href="/buyer/bulk?new=1" className="inline-flex items-center gap-2 px-5 py-2.5 bg-white/15 text-white font-semibold rounded-lg hover:bg-white/25 transition-colors">
              <Plus className="w-4 h-4" /> New Bulk Order
            </Link>
          </div>
        </div>
        <Package className="absolute -right-6 -bottom-8 w-52 h-52 text-white/10 pointer-events-none" />
      </div>

      {/* Attention banner — orders needing the customer's action */}
      {!loading && awaitingApproval > 0 && (
        <Link href="/buyer/bulk" className="flex items-center justify-between gap-4 rounded-2xl border border-purple-200 bg-purple-50 px-5 py-4 hover:bg-purple-100/70 transition-colors">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <p className="font-semibold text-purple-900">
                {awaitingApproval} order{awaitingApproval > 1 ? "s" : ""} awaiting your approval
              </p>
              <p className="text-sm text-purple-700">Review the proposed timeline and confirm to start production.</p>
            </div>
          </div>
          <ChevronRight className="w-5 h-5 text-purple-500 shrink-0" />
        </Link>
      )}

      {/* Customer stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s) => (
          <Link key={s.label} href={s.href} className="bg-white rounded-2xl border border-slate-200 p-5 hover:shadow-md hover:border-blue-200 transition-all">
            <div className={`w-11 h-11 rounded-xl flex items-center justify-center mb-3 ${s.tint}`}>
              <s.icon className="w-5 h-5" />
            </div>
            <p className="text-3xl font-bold text-slate-900">{loading ? "–" : s.value}</p>
            <p className="text-sm text-slate-500 mt-0.5">{s.label}</p>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Quick actions */}
        <div className="lg:col-span-2 space-y-5">
          <div className="rounded-2xl border border-slate-200 bg-white p-6">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
                <ClipboardList className="w-6 h-6" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-bold text-slate-900">Request a sample</h3>
                <p className="text-sm text-slate-600 mt-1 mb-4">
                  Tell us the style and date — you'll get an instant feasibility answer and the best factory to make it.
                </p>
                <div className="flex flex-wrap gap-3">
                  <Link href="/buyer/samples?new=1">
                    <span className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors">
                      <Plus className="w-4 h-4" /> New Sample Request
                    </span>
                  </Link>
                  <Link href="/buyer/samples">
                    <span className="inline-flex items-center gap-2 px-4 py-2 border border-slate-200 text-slate-700 text-sm font-semibold rounded-lg hover:bg-slate-50 transition-colors">
                      View my samples
                    </span>
                  </Link>
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-6">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                <Package className="w-6 h-6" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-bold text-slate-900">Place a bulk order</h3>
                <p className="text-sm text-slate-600 mt-1 mb-4">
                  Turn an approved style into production. We'll match it to the factory best able to hit your delivery date.
                </p>
                <div className="flex flex-wrap gap-3">
                  <Link href="/buyer/bulk?new=1">
                    <span className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg transition-colors">
                      <Plus className="w-4 h-4" /> New Bulk Order
                    </span>
                  </Link>
                  <Link href="/buyer/bulk">
                    <span className="inline-flex items-center gap-2 px-4 py-2 border border-slate-200 text-slate-700 text-sm font-semibold rounded-lg hover:bg-slate-50 transition-colors">
                      Track production
                    </span>
                  </Link>
                </div>
              </div>
            </div>
          </div>

          {/* Help card */}
          <div className="rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-50 to-blue-50 p-6 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-11 h-11 rounded-xl bg-white text-blue-600 flex items-center justify-center border border-blue-100">
                <LifeBuoy className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-semibold text-slate-900">Need a hand?</h3>
                <p className="text-sm text-slate-600">Our team is happy to help with any order question.</p>
              </div>
            </div>
            <Link href="/contact" className="text-sm font-semibold text-blue-600 hover:text-blue-700 shrink-0 inline-flex items-center gap-1">
              Contact us <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>

        {/* Recent orders */}
        <div className="rounded-2xl border border-slate-200 bg-white p-6 flex flex-col">
          <h3 className="text-lg font-bold text-slate-900 mb-4">Recent orders</h3>
          <div className="flex-1">
            {loading ? (
              <p className="text-sm text-slate-500 text-center py-6">Loading…</p>
            ) : recent.length === 0 ? (
              <div className="text-center py-8">
                <div className="mx-auto w-12 h-12 bg-slate-50 rounded-full flex items-center justify-center mb-3">
                  <Package className="w-5 h-5 text-slate-400" />
                </div>
                <p className="text-sm text-slate-500">No orders yet.</p>
                <Link href="/buyer/samples?new=1" className="text-blue-600 text-sm font-medium hover:underline mt-2 inline-block">
                  Request your first sample →
                </Link>
              </div>
            ) : (
              <ul className="divide-y divide-slate-100">
                {recent.map((order) => {
                  const pill = order.type === "Bulk" ? BULK_PILL[order.status] : SAMPLE_PILL[order.status];
                  const label = order.type === "Bulk" ? bulkLabel(order.status) : order.status;
                  const href = order.type === "Bulk" ? "/buyer/bulk" : "/buyer/samples";
                  return (
                    <li key={`${order.type}-${order.id}`} className="py-3">
                      <Link href={href} className="flex items-center justify-between gap-3 group">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-slate-800 truncate">
                            {order.type} · {order.style_number}
                          </p>
                          <p className="text-xs text-slate-400">
                            {order.created_at ? new Date(order.created_at).toLocaleDateString() : ""}
                          </p>
                        </div>
                        <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full whitespace-nowrap ${pill || "bg-slate-100 text-slate-600"}`}>
                          {label}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
          <div className="mt-4 pt-4 border-t border-slate-100">
            <Link href="/buyer/notifications" className="text-sm text-blue-600 font-medium hover:text-blue-700 flex items-center justify-center group">
              <Bell className="w-4 h-4 mr-1.5" /> View all notifications
              <ArrowRight className="w-4 h-4 ml-1 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
