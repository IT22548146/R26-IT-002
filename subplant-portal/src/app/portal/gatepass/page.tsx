"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import api from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Field, Pill, fmtDate } from "@/components/ui/bits";
import { Truck, Plus, Trash2, Info } from "lucide-react";

const DISPATCH = ["Pending", "Dispatched", "Received"];

interface OrderOption {
  id: number;
  order_number: string;
}

interface CustomerOption {
  id: number;
  customer_name: string;
}

interface GatepassRecord {
  id: number;
  gatepass_number: string;
  gatepass_date: string;
  customer_name?: string | null;
  style_number?: string | null;
  good_qty: number;
  damage_qty: number;
  total_qty: number;
  dispatch_status: string;
}

export default function GatepassPage() {
  const [rows, setRows] = useState<GatepassRecord[]>([]);
  const [orders, setOrders] = useState<OrderOption[]>([]);
  const [customers, setCustomers] = useState<CustomerOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  const load = async () => {
    try {
      const [g, o, c] = await Promise.all([
        api.get("/subplant/gatepasses"),
        api.get("/subplant/orders"),
        api.get("/subplant/customers"),
      ]);
      setRows(g.data); setOrders(o.data); setCustomers(c.data);
    } catch { /* interceptor */ } finally { setLoading(false); }
  };
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const remove = async (gatepass: GatepassRecord) => {
    const r = await Swal.fire({ icon: "warning", title: `Delete gatepass ${gatepass.gatepass_number}?`,
      text: "The day's production figures will be recalculated.",
      showCancelButton: true, confirmButtonText: "Delete", confirmButtonColor: "#dc2626" });
    if (!r.isConfirmed) return;
    try {
      await api.delete(`/subplant/gatepasses/${gatepass.id}`);
      Swal.fire({ icon: "success", title: "Gatepass deleted" }); load();
    } catch (err: unknown) {
      Swal.fire({ icon: "error", title: "Error", text: getApiErrorMessage(err, "Delete failed.") });
    }
  };

  const totals = rows.reduce((a, g) => ({
    good: a.good + (g.good_qty || 0),
    dmg: a.dmg + (g.damage_qty || 0),
  }), { good: 0, dmg: 0 });
  const totalAll = totals.good + totals.dmg;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <Truck className="w-6 h-6 mr-2 text-teal-600" /> Gatepass Management
        </h2>
        <Button onClick={() => setShowForm(true)} className="bg-teal-600 hover:bg-teal-700">
          <Plus className="w-4 h-4 mr-1" /> Record Gatepass
        </Button>
      </div>

      <div className="rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800 flex items-start gap-2">
        <Info className="w-4 h-4 mt-0.5 shrink-0" />
        <span>
          Gatepasses are your production record. Good and damaged quantities are sent to FabricFlow
          and used to calculate your plant&apos;s output, damage percentage and performance score.
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SummaryTile label="Total Dispatched" value={totals.good.toLocaleString()} tone="text-emerald-600" />
        <SummaryTile label="Total Damaged" value={totals.dmg.toLocaleString()} tone="text-red-600" />
        <SummaryTile label="Damage Rate"
                     value={totalAll ? `${((totals.dmg / totalAll) * 100).toFixed(2)}%` : "—"}
                     tone={totalAll && (totals.dmg / totalAll) * 100 > 3 ? "text-red-600" : "text-slate-900"}
                     sub="acceptable limit 3%" />
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
          <h3 className="font-semibold text-slate-800">Gatepass Records</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase text-slate-500 bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-4 py-3">Gatepass</th>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Customer</th>
                <th className="px-4 py-3">Style</th>
                <th className="px-4 py-3 text-right">Good</th>
                <th className="px-4 py-3 text-right">Damage</th>
                <th className="px-4 py-3 text-right">Total</th>
                <th className="px-4 py-3">Dispatch</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr><td colSpan={9} className="px-4 py-8 text-center text-slate-500">Loading...</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={9} className="px-4 py-8 text-center text-slate-500">No gatepasses recorded yet.</td></tr>
              ) : rows.map((g) => (
                <tr key={g.id} className="hover:bg-slate-50/60">
                  <td className="px-4 py-3 font-medium text-slate-900">{g.gatepass_number}</td>
                  <td className="px-4 py-3 text-slate-600">{fmtDate(g.gatepass_date)}</td>
                  <td className="px-4 py-3 text-slate-600">{g.customer_name || "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{g.style_number || "—"}</td>
                  <td className="px-4 py-3 text-right text-emerald-600 font-medium">{Number(g.good_qty).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right text-red-600">{Number(g.damage_qty).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right text-slate-900">{Number(g.total_qty).toLocaleString()}</td>
                  <td className="px-4 py-3"><Pill value={g.dispatch_status} /></td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => remove(g)} className="text-slate-400 hover:text-red-600 p-1" title="Delete">
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
        <GatepassModal orders={orders} customers={customers}
                       onClose={() => setShowForm(false)}
                       onSaved={() => { setShowForm(false); load(); }} />
      )}
    </div>
  );
}

function SummaryTile({ label, value, tone, sub }: { label: string; value: string; tone: string; sub?: string }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${tone}`}>{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function GatepassModal({ orders, customers, onClose, onSaved }: {
  orders: OrderOption[];
  customers: CustomerOption[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({
    gatepass_number: "", gatepass_date: today, order_id: "", customer_id: "",
    style_number: "", description: "", good_qty: "", damage_qty: "0",
    dispatch_status: "Dispatched",
  });
  const [saving, setSaving] = useState(false);

  const good = Number(form.good_qty || 0);
  const dmg = Number(form.damage_qty || 0);
  const total = good + dmg;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.gatepass_number.trim()) {
      Swal.fire({ icon: "warning", title: "Gatepass number is required." }); return;
    }
    if (total <= 0) {
      Swal.fire({ icon: "warning", title: "Enter at least one good or damaged piece." }); return;
    }
    if (form.gatepass_date < today) {
      Swal.fire({ icon: "warning", title: "Gatepass date cannot be in the past." }); return;
    }
    setSaving(true);
    try {
      const res = await api.post("/subplant/gatepasses", {
        ...form,
        order_id: form.order_id || null,
        customer_id: form.customer_id || null,
        good_qty: good, damage_qty: dmg,
      });
      Swal.fire({
        icon: "success", title: "Gatepass recorded",
        text: `Production for ${res.data.daily_log_updated} sent to FabricFlow.`,
      });
      onSaved();
    } catch (err: unknown) {
      Swal.fire({ icon: "error", title: "Error", text: getApiErrorMessage(err, "Save failed.") });
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <form onSubmit={submit} className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-lg p-6"
            onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Record Gatepass</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Gatepass Number *">
            <Input required value={form.gatepass_number}
                   onChange={(e) => setForm({ ...form, gatepass_number: e.target.value })} placeholder="GP-001" />
          </Field>
          <Field label="Date *">
            <Input type="date" min={today} required value={form.gatepass_date}
                   onChange={(e) => setForm({ ...form, gatepass_date: e.target.value })} />
          </Field>
          <Field label="Order">
            <select className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900"
                    value={form.order_id} onChange={(e) => setForm({ ...form, order_id: e.target.value })}>
              <option value="">Select order…</option>
              {orders.map((o) => <option key={o.id} value={o.id}>{o.order_number}</option>)}
            </select>
          </Field>
          <Field label="Customer">
            <select className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900"
                    value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: e.target.value })}>
              <option value="">Select customer…</option>
              {customers.map((c) => <option key={c.id} value={c.id}>{c.customer_name}</option>)}
            </select>
          </Field>
          <Field label="Style Number">
            <Input value={form.style_number}
                   onChange={(e) => setForm({ ...form, style_number: e.target.value })} placeholder="ST-900" />
          </Field>
          <Field label="Dispatch Status">
            <select className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900"
                    value={form.dispatch_status}
                    onChange={(e) => setForm({ ...form, dispatch_status: e.target.value })}>
              {DISPATCH.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="Good Quantity *">
            <Input type="number" min="0" required value={form.good_qty}
                   onChange={(e) => setForm({ ...form, good_qty: e.target.value })} placeholder="480" />
          </Field>
          <Field label="Damage Quantity">
            <Input type="number" min="0" value={form.damage_qty}
                   onChange={(e) => setForm({ ...form, damage_qty: e.target.value })} placeholder="0" />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Description">
              <Input value={form.description}
                     onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Optional" />
            </Field>
          </div>
        </div>

        <div className="bg-slate-50 border border-slate-100 rounded-lg p-3 text-sm text-slate-600 mt-4 flex justify-between">
          <span>Total quantity</span>
          <span className="font-semibold text-slate-900">
            {total.toLocaleString()}
            {total > 0 && <span className="text-xs text-slate-500 ml-2">({((dmg / total) * 100).toFixed(2)}% damage)</span>}
          </span>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving} className="bg-teal-600 hover:bg-teal-700">
            {saving ? "Saving..." : "Record Gatepass"}
          </Button>
        </div>
      </form>
    </div>
  );
}
