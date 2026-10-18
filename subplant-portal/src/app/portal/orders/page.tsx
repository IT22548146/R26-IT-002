"use client";
import Swal from "@/lib/swal";

import { useState, useEffect, useMemo } from "react";
import api from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Field, Card, Empty, Stat, fmtDate } from "@/components/ui/bits";
import { ClipboardList, Plus, Package, Gauge, Clock, Trash2 } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";

const STATUSES = ["Draft", "Confirmed", "In Progress", "Completed", "Cancelled"];
const COLORS = ["#94a3b8", "#0ea5e9", "#f59e0b", "#10b981", "#ef4444"];

interface CustomerOption {
  id: number;
  customer_name: string;
}

interface OrderRecord {
  id: number;
  order_number: string;
  customer_name?: string | null;
  order_quantity: number;
  dispatched_qty?: number | null;
  planned_start?: string | null;
  planned_finish?: string | null;
  status: string;
}

interface StatusChartValue {
  name: string;
  value: number;
}

interface OrderTrendValue {
  month: string;
  qty: number;
}

interface OrderStats {
  orders_this_month: number;
  planned_quantity: number;
  avg_daily_commitment: number;
  on_time_rate: number | null;
  trend: OrderTrendValue[];
  by_status: StatusChartValue[];
}

export default function OrdersPage() {
  const [rows, setRows] = useState<OrderRecord[]>([]);
  const [customers, setCustomers] = useState<CustomerOption[]>([]);
  const [stats, setStats] = useState<OrderStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  const load = async () => {
    try {
      const [list, cust, st] = await Promise.all([
        api.get("/subplant/orders"),
        api.get("/subplant/customers"),
        api.get("/subplant/orders/stats"),
      ]);
      setRows(list.data); setCustomers(cust.data); setStats(st.data);
    } catch { /* interceptor */ } finally { setLoading(false); }
  };
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const setStatus = async (order: OrderRecord, status: string) => {
    try {
      await api.put(`/subplant/orders/${order.id}`, { status });
      Swal.fire({ icon: "success", title: `Order ${status}` });
      load();
    } catch (err: unknown) {
      Swal.fire({ icon: "error", title: "Error", text: getApiErrorMessage(err, "Update failed.") });
    }
  };

  const remove = async (order: OrderRecord) => {
    const r = await Swal.fire({ icon: "warning", title: `Delete order ${order.order_number}?`,
      showCancelButton: true, confirmButtonText: "Delete", confirmButtonColor: "#dc2626" });
    if (!r.isConfirmed) return;
    try {
      await api.delete(`/subplant/orders/${order.id}`);
      Swal.fire({ icon: "success", title: "Order deleted" }); load();
    } catch (err: unknown) {
      Swal.fire({ icon: "error", title: "Error", text: getApiErrorMessage(err, "Delete failed.") });
    }
  };

  return (
    <div className="space-y-6 text-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <ClipboardList className="w-6 h-6 mr-2 text-teal-600" /> New Order Register
        </h2>
        <Button onClick={() => setShowForm(true)} className="bg-teal-600 hover:bg-teal-700">
          <Plus className="w-4 h-4 mr-1" /> Register Order
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat icon={<ClipboardList className="w-5 h-5" />} label="Orders This Month" value={stats?.orders_this_month ?? "-"} tone="teal" />
        <Stat icon={<Package className="w-5 h-5" />} label="Planned Quantity"
              value={stats ? Number(stats.planned_quantity).toLocaleString() : "-"} tone="indigo" />
        <Stat icon={<Gauge className="w-5 h-5" />} label="Avg Daily Commitment"
              value={stats?.avg_daily_commitment ?? "-"} sub="pcs/day" tone="blue" />
        <Stat icon={<Clock className="w-5 h-5" />} label="On-Time Completion"
              value={stats?.on_time_rate != null ? `${Math.round(stats.on_time_rate * 100)}%` : "—"} tone="emerald" />
      </div>

      {stats && (stats.trend?.length > 0 || stats.by_status?.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card title="Order Quantity Trend">
            {stats.trend?.length ? (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={stats.trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#64748b" }} />
                  <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
                  <Tooltip contentStyle={{ borderRadius: '8px', color: '#0f172a' }} itemStyle={{ color: '#0f172a' }} />
                  <Bar dataKey="qty" fill="#0d9488" radius={[4, 4, 0, 0]} name="Quantity" />
                </BarChart>
              </ResponsiveContainer>
            ) : <Empty text="No orders yet." />}
          </Card>
          <Card title="Order Status Distribution">
            {stats.by_status?.length ? (
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={stats.by_status} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={{ fill: '#475569', fontSize: 12 }}>
                    {stats.by_status.map((entry, index) => (
                      <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ borderRadius: '8px', color: '#0f172a' }} itemStyle={{ color: '#0f172a' }} /><Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : <Empty text="No orders yet." />}
          </Card>
        </div>
      )}

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
          <h3 className="font-semibold text-slate-800">Recent Orders</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase text-slate-500 bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-4 py-3">Order</th>
                <th className="px-4 py-3">Customer</th>
                <th className="px-4 py-3 text-right">Qty</th>
                <th className="px-4 py-3 text-right">Dispatched</th>
                <th className="px-4 py-3">Planned</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">Loading...</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">No orders registered yet.</td></tr>
              ) : rows.map((o) => (
                <tr key={o.id} className="hover:bg-slate-50/60">
                  <td className="px-4 py-3 font-medium text-slate-900">{o.order_number}</td>
                  <td className="px-4 py-3 text-slate-600">{o.customer_name || "—"}</td>
                  <td className="px-4 py-3 text-right">{Number(o.order_quantity).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right text-slate-600">{Number(o.dispatched_qty || 0).toLocaleString()}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {fmtDate(o.planned_start)} → {fmtDate(o.planned_finish)}
                  </td>
                  <td className="px-4 py-3">
                    <select
                      className="text-xs border border-slate-300 rounded-md py-1 px-1.5 bg-white"
                      value={o.status}
                      onChange={(e) => setStatus(o, e.target.value)}
                    >
                      {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => remove(o)} className="text-slate-400 hover:text-red-600 p-1" title="Delete">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {showForm && (
        <OrderModal customers={customers} onClose={() => setShowForm(false)}
                    onSaved={() => { setShowForm(false); load(); }} />
      )}
    </div>
  );
}

function OrderModal({ customers, onClose, onSaved }: {
  customers: CustomerOption[]; onClose: () => void; onSaved: () => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({
    order_number: "", customer_id: "", order_date: today, order_quantity: "",
    planned_start: "", planned_finish: "", status: "Draft", notes: "",
  });
  const [saving, setSaving] = useState(false);
  const minFinishDate = useMemo(() => {
    const quantity = Number(form.order_quantity);
    if (!form.planned_start || !Number.isFinite(quantity) || quantity <= 0) {
      return today;
    }

    const bufferedQuantity = Math.ceil(quantity * 1.04);
    const daysRequired = Math.ceil(bufferedQuantity / 500);
    const finishDate = new Date(`${form.planned_start}T00:00:00Z`);
    if (Number.isNaN(finishDate.getTime())) {
      return today;
    }

    finishDate.setUTCDate(finishDate.getUTCDate() + Math.max(0, daysRequired - 1));
    const calculatedMinimum = finishDate.toISOString().slice(0, 10);
    return calculatedMinimum < today ? today : calculatedMinimum;
  }, [form.order_quantity, form.planned_start, today]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.order_number.trim() || Number(form.order_quantity) <= 0) {
      Swal.fire({ icon: "warning", title: "Enter an order number and a quantity above zero." });
      return;
    }
    if (form.planned_start && form.planned_finish && form.planned_finish < form.planned_start) {
      Swal.fire({ icon: "warning", title: "Planned finish cannot be before planned start." });
      return;
    }
    if (form.order_date < today) {
      Swal.fire({ icon: "warning", title: "Order date cannot be in the past." });
      return;
    }
    if (form.planned_start && form.planned_start < today) {
      Swal.fire({ icon: "warning", title: "Planned start cannot be in the past." });
      return;
    }
    if (form.planned_finish && form.planned_finish < minFinishDate) {
      Swal.fire({
        icon: "warning",
        title: `Based on capacity (500/day + 4% defect), finish date must be at least ${minFinishDate}.`,
      });
      return;
    }
    setSaving(true);
    try {
      await api.post("/subplant/orders", {
        ...form,
        customer_id: form.customer_id || null,
        order_quantity: Number(form.order_quantity),
      });
      Swal.fire({ icon: "success", title: "Order registered" });
      onSaved();
    } catch (err: unknown) {
      Swal.fire({ icon: "error", title: "Error", text: getApiErrorMessage(err, "Save failed.") });
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <form onSubmit={submit} className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-lg p-6"
            onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Register New Order</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Order Number *">
            <Input required value={form.order_number}
                   onChange={(e) => setForm({ ...form, order_number: e.target.value })} placeholder="LMC-001" />
          </Field>
          <Field label="Customer">
            <select className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900"
                    value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: e.target.value })}>
              <option value="">Select customer…</option>
              {customers.map((c) => <option key={c.id} value={c.id}>{c.customer_name}</option>)}
            </select>
          </Field>
          <Field label="Order Date">
            <Input type="date" min={today} value={form.order_date}
                   onChange={(e) => setForm({ ...form, order_date: e.target.value })} />
          </Field>
          <Field label="Order Quantity *">
            <Input type="number" min="1" required value={form.order_quantity}
                   onChange={(e) => setForm({ ...form, order_quantity: e.target.value })} placeholder="5000" />
          </Field>
          <Field label="Planned Start">
            <Input type="date" min={today} value={form.planned_start}
                   onChange={(e) => setForm({ ...form, planned_start: e.target.value })} />
          </Field>
          <Field label="Planned Finish">
            <Input type="date" min={minFinishDate} value={form.planned_finish}
                   onChange={(e) => setForm({ ...form, planned_finish: e.target.value })} />
          </Field>
          <Field label="Status">
            <select className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900"
                    value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <div className="sm:col-span-2">
            <Field label="Notes">
              <Input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })}
                     placeholder="Optional" />
            </Field>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving} className="bg-teal-600 hover:bg-teal-700">
            {saving ? "Saving..." : "Register Order"}
          </Button>
        </div>
      </form>
    </div>
  );
}
