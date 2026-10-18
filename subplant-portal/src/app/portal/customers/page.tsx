"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import api from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Field, Card, Empty, Stat } from "@/components/ui/bits";
import { Users, Plus, Search, Trash2, UserCheck, UserPlus, Wallet } from "lucide-react";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
} from "recharts";

const COLORS = ["#0d9488", "#0ea5e9", "#6366f1", "#f59e0b", "#ef4444", "#8b5cf6"];

interface Customer {
  id: number;
  customer_name: string;
  customer_code?: string | null;
  customer_type?: string | null;
  location?: string | null;
  contact_no?: string | null;
  order_count: number;
  balance: number;
}

interface ChartValue {
  name: string;
  value: number;
}

interface CustomerTrend {
  month: string;
  count: number;
}

interface CustomerStats {
  total_customers: number;
  active_customers: number;
  new_this_month: number;
  pending_payment_customers: number;
  by_type: ChartValue[];
  over_time: CustomerTrend[];
}

export default function CustomersPage() {
  const [rows, setRows] = useState<Customer[]>([]);
  const [stats, setStats] = useState<CustomerStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);

  const load = async () => {
    try {
      const [list, st] = await Promise.all([
        api.get("/subplant/customers"),
        api.get("/subplant/customers/stats"),
      ]);
      setRows(list.data);
      setStats(st.data);
    } catch {
      /* handled by interceptor */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const remove = async (c: Customer) => {
    const r = await Swal.fire({
      icon: "warning", title: `Delete ${c.customer_name}?`,
      showCancelButton: true, confirmButtonText: "Delete", confirmButtonColor: "#dc2626",
    });
    if (!r.isConfirmed) return;
    try {
      await api.delete(`/subplant/customers/${c.id}`);
      Swal.fire({ icon: "success", title: "Customer deleted" });
      load();
    } catch (err: unknown) {
      Swal.fire({ icon: "error", title: "Error", text: getApiErrorMessage(err, "Delete failed.") });
    }
  };

  const filtered = rows.filter((c) =>
    (c.customer_name || "").toLowerCase().includes(search.toLowerCase()) ||
    (c.location || "").toLowerCase().includes(search.toLowerCase()) ||
    (c.customer_type || "").toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6 text-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <Users className="w-6 h-6 mr-2 text-teal-600" /> Customer Register
        </h2>
        <Button onClick={() => setShowForm(true)} className="bg-teal-600 hover:bg-teal-700">
          <Plus className="w-4 h-4 mr-1" /> Register Customer
        </Button>
      </div>

      {/* Dashboard figures */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat icon={<Users className="w-5 h-5" />} label="Total Customers" value={stats?.total_customers ?? "-"} tone="teal" />
        <Stat icon={<UserCheck className="w-5 h-5" />} label="Active" value={stats?.active_customers ?? "-"} tone="emerald" />
        <Stat icon={<UserPlus className="w-5 h-5" />} label="New This Month" value={stats?.new_this_month ?? "-"} tone="blue" />
        <Stat icon={<Wallet className="w-5 h-5" />} label="Pending Payments" value={stats?.pending_payment_customers ?? "-"} tone="amber" />
      </div>

      {/* Charts */}
      {stats && (stats.by_type?.length > 0 || stats.over_time?.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card title="Customer Type Distribution">
            {stats.by_type?.length ? (
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={stats.by_type} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={{ fill: '#475569', fontSize: 12 }}>
                    {stats.by_type.map((entry, index) => (
                      <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ borderRadius: '8px', color: '#0f172a' }} itemStyle={{ color: '#0f172a' }} /><Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : <Empty text="No customers yet." />}
          </Card>
          <Card title="New Customers Over Time">
            {stats.over_time?.length ? (
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={stats.over_time}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#64748b" }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#64748b" }} />
                  <Tooltip contentStyle={{ borderRadius: '8px', color: '#0f172a' }} itemStyle={{ color: '#0f172a' }} />
                  <Line type="monotone" dataKey="count" stroke="#0d9488" strokeWidth={2} name="New customers" />
                </LineChart>
              </ResponsiveContainer>
            ) : <Empty text="No history yet." />}
          </Card>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 bg-slate-50 flex items-center justify-between gap-3">
          <h3 className="font-semibold text-slate-800">Registered Customers</h3>
          <div className="relative w-full max-w-xs">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Search className="h-4 w-4 text-slate-400" />
            </div>
            <Input className="pl-10" placeholder="Search customers..." value={search}
                   onChange={(e) => setSearch(e.target.value)} />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase text-slate-500 bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-4 py-3">Customer</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Location</th>
                <th className="px-4 py-3">Contact</th>
                <th className="px-4 py-3 text-right">Orders</th>
                <th className="px-4 py-3 text-right">Balance</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">Loading...</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">No customers registered yet.</td></tr>
              ) : filtered.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50/60">
                  <td className="px-4 py-3">
                    <p className="font-medium text-slate-900">{c.customer_name}</p>
                    {c.customer_code && <p className="text-xs text-slate-400">{c.customer_code}</p>}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{c.customer_type || "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{c.location || "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{c.contact_no || "—"}</td>
                  <td className="px-4 py-3 text-right">{c.order_count}</td>
                  <td className={`px-4 py-3 text-right font-medium ${c.balance > 0 ? "text-amber-600" : "text-slate-500"}`}>
                    {Number(c.balance || 0).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => remove(c)} className="text-slate-400 hover:text-red-600 p-1" title="Delete">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {showForm && <CustomerModal onClose={() => setShowForm(false)} onSaved={() => { setShowForm(false); load(); }} />}
    </div>
  );
}

function CustomerModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({
    customer_name: "", customer_code: "", customer_type: "", contact_no: "",
    location: "", registered_date: today,
  });
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.customer_name.trim()) {
      Swal.fire({ icon: "warning", title: "Customer name is required." });
      return;
    }
    setSaving(true);
    try {
      await api.post("/subplant/customers", form);
      Swal.fire({ icon: "success", title: "Customer registered" });
      onSaved();
    } catch (err: unknown) {
      Swal.fire({ icon: "error", title: "Error", text: getApiErrorMessage(err, "Save failed.") });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <form onSubmit={submit} className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-lg p-6"
            onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Register Customer</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Customer Name *">
            <Input required value={form.customer_name}
                   onChange={(e) => setForm({ ...form, customer_name: e.target.value })} placeholder="e.g. Hirdaramani" />
          </Field>
          <Field label="Customer ID / Code">
            <Input value={form.customer_code}
                   onChange={(e) => setForm({ ...form, customer_code: e.target.value })} placeholder="CUS-001" />
          </Field>
          <Field label="Customer Type">
            <Input value={form.customer_type}
                   onChange={(e) => setForm({ ...form, customer_type: e.target.value })} placeholder="Garment Exporter" />
          </Field>
          <Field label="Contact Number">
            <Input value={form.contact_no}
                   onChange={(e) => setForm({ ...form, contact_no: e.target.value })} placeholder="+94 77 123 4567" />
          </Field>
          <Field label="Location">
            <Input value={form.location}
                   onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="Colombo" />
          </Field>
          <Field label="Date">
            <Input type="date" value={form.registered_date}
                   onChange={(e) => setForm({ ...form, registered_date: e.target.value })} />
          </Field>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving} className="bg-teal-600 hover:bg-teal-700">
            {saving ? "Saving..." : "Register"}
          </Button>
        </div>
      </form>
    </div>
  );
}
