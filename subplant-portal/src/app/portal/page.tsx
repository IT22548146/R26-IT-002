"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Users, ClipboardList, Package, Wallet, ArrowRight, Truck, Receipt } from "lucide-react";

interface DashboardStats {
  total_customers: number;
  open_orders: number;
  output_this_month: number;
  damage_rate: number;
  pending_payment: number;
}

export default function PortalDashboard() {
  const { plant } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/subplant/dashboard")
      .then((r) => setStats(r.data))
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      {/* Welcome */}
      <div className="bg-gradient-to-r from-teal-800 to-teal-950 rounded-xl shadow-lg p-8 text-white">
        <h2 className="text-2xl font-bold mb-1">{plant?.name || "Sub Plant Portal"}</h2>
        <p className="text-teal-100 text-sm">
          Record your customers, orders and dispatches here. Your production data is shared with
          FabricFlow and used to score your plant&apos;s performance.
        </p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi icon={<Users className="w-5 h-5" />} tone="teal" label="Customers"
             value={loading ? "-" : stats?.total_customers ?? 0} />
        <Kpi icon={<ClipboardList className="w-5 h-5" />} tone="blue" label="Open Orders"
             value={loading ? "-" : stats?.open_orders ?? 0} />
        <Kpi icon={<Package className="w-5 h-5" />} tone="indigo" label="Output This Month"
             value={loading ? "-" : (stats?.output_this_month ?? 0).toLocaleString()}
             sub={stats ? `${stats.damage_rate}% damage` : ""} />
        <Kpi icon={<Wallet className="w-5 h-5" />} tone="amber" label="Pending Payment"
             value={loading ? "-" : `Rs. ${(stats?.pending_payment ?? 0).toLocaleString()}`} />
      </div>

      {/* Quick links */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <QuickLink href="/portal/orders" icon={<ClipboardList className="w-6 h-6" />}
                   title="Register an Order" desc="Log a new production order for a customer" />
        <QuickLink href="/portal/gatepass" icon={<Truck className="w-6 h-6" />}
                   title="Record a Gatepass" desc="Dispatch quantities — feeds your performance score" />
        <QuickLink href="/portal/invoices" icon={<Receipt className="w-6 h-6" />}
                   title="Create an Invoice" desc="Bill a customer and track payments" />
      </div>
    </div>
  );
}

function Kpi({ icon, label, value, sub, tone }: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  sub?: string;
  tone: string;
}) {
  const tones: Record<string, string> = {
    teal: "bg-teal-50 text-teal-600",
    blue: "bg-blue-50 text-blue-600",
    indigo: "bg-indigo-50 text-indigo-600",
    amber: "bg-amber-50 text-amber-600",
  };
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center mb-3 ${tones[tone]}`}>{icon}</div>
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-slate-900 mt-1">{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function QuickLink({ href, icon, title, desc }: {
  href: string; icon: React.ReactNode; title: string; desc: string;
}) {
  return (
    <Link href={href}
          className="group bg-white rounded-xl border border-slate-200 shadow-sm p-5 hover:border-teal-300 hover:shadow-md transition-all flex items-start gap-4">
      <div className="p-3 bg-teal-50 text-teal-600 rounded-lg group-hover:bg-teal-600 group-hover:text-white transition-colors shrink-0">
        {icon}
      </div>
      <div className="min-w-0">
        <h3 className="font-bold text-slate-800 flex items-center gap-1">
          {title} <ArrowRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
        </h3>
        <p className="text-xs text-slate-500 mt-1">{desc}</p>
      </div>
    </Link>
  );
}
