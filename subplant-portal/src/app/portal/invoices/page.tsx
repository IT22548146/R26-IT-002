"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import api from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Field, Card, Empty, Stat, Pill, fmtDate, money } from "@/components/ui/bits";
import { Receipt, Plus, Wallet, TrendingUp, CircleDollarSign, Printer, HandCoins } from "lucide-react";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";

const STATUS_COLOR: Record<string, string> = {
  Paid: "#10b981", Partial: "#0ea5e9", Pending: "#f59e0b", Overdue: "#ef4444",
};

interface CustomerOption {
  id: number;
  customer_name: string;
}

interface InvoiceRecord {
  id: number;
  invoice_number: string;
  customer_name?: string | null;
  invoice_date: string;
  total_price: number;
  paid_amount: number;
  balance: number;
  payment_status: string;
}

interface InvoiceDetails extends InvoiceRecord {
  location?: string | null;
  description?: string | null;
  amount: number;
  discount: number;
}

interface PaymentStatusValue {
  name: string;
  value: number;
}

interface IncomeTrendValue {
  month: string;
  billed: number;
  collected: number;
}

interface InvoiceStats {
  monthly_income: number;
  yearly_income: number;
  paid_amount: number;
  pending_amount: number;
  by_status: PaymentStatusValue[];
  income_trend: IncomeTrendValue[];
}

export default function InvoicesPage() {
  const [rows, setRows] = useState<InvoiceRecord[]>([]);
  const [customers, setCustomers] = useState<CustomerOption[]>([]);
  const [stats, setStats] = useState<InvoiceStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [payFor, setPayFor] = useState<InvoiceRecord | null>(null);

  const load = async () => {
    try {
      const [inv, cust, st] = await Promise.all([
        api.get("/subplant/invoices"),
        api.get("/subplant/customers"),
        api.get("/subplant/invoices/stats"),
      ]);
      setRows(inv.data); setCustomers(cust.data); setStats(st.data);
    } catch { /* interceptor */ } finally { setLoading(false); }
  };
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const printInvoice = async (invoice: InvoiceRecord) => {
    try {
      const res = await api.get(`/subplant/invoices/${invoice.id}`);
      const d = res.data.invoice as InvoiceDetails;
      const w = window.open("", "_blank", "width=800,height=900");
      if (!w) {
        Swal.fire({ icon: "info", title: "Allow pop-ups to print the invoice." });
        return;
      }
      w.document.write(`
        <html><head><title>Invoice ${d.invoice_number}</title>
        <style>
          body{font-family:system-ui,sans-serif;padding:40px;color:#0f172a}
          h1{margin:0 0 4px;font-size:24px} .muted{color:#64748b;font-size:13px}
          table{width:100%;border-collapse:collapse;margin-top:24px}
          th,td{text-align:left;padding:10px;border-bottom:1px solid #e2e8f0;font-size:14px}
          .right{text-align:right} .total{font-weight:700;font-size:16px}
        </style></head><body>
        <h1>Invoice ${d.invoice_number}</h1>
        <p class="muted">Date: ${new Date(d.invoice_date).toLocaleDateString()}</p>
        <p class="muted">Bill to: <strong>${d.customer_name || "-"}</strong>${d.location ? " · " + d.location : ""}</p>
        <table>
          <tr><th>Description</th><th class="right">Amount</th></tr>
          <tr><td>${d.description || "Production services"}</td><td class="right">${Number(d.amount).toFixed(2)}</td></tr>
          <tr><td>Discount</td><td class="right">-${Number(d.discount).toFixed(2)}</td></tr>
          <tr><td class="total">Total</td><td class="right total">${Number(d.total_price).toFixed(2)}</td></tr>
          <tr><td>Paid</td><td class="right">${Number(d.paid_amount).toFixed(2)}</td></tr>
          <tr><td class="total">Balance</td><td class="right total">${(Number(d.total_price) - Number(d.paid_amount)).toFixed(2)}</td></tr>
        </table>
        <p class="muted" style="margin-top:32px">Status: ${d.payment_status}</p>
        </body></html>`);
      w.document.close();
      w.print();
    } catch {
      Swal.fire({ icon: "error", title: "Could not open the invoice." });
    }
  };

  return (
    <div className="space-y-6 text-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <Receipt className="w-6 h-6 mr-2 text-teal-600" /> Invoices &amp; Payments
        </h2>
        <Button onClick={() => setShowForm(true)} className="bg-teal-600 hover:bg-teal-700">
          <Plus className="w-4 h-4 mr-1" /> Create Invoice
        </Button>
      </div>

      {/* Financial dashboard */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat icon={<CircleDollarSign className="w-5 h-5" />} label="Monthly Income"
              value={stats ? money(stats.monthly_income) : "-"} tone="teal" />
        <Stat icon={<TrendingUp className="w-5 h-5" />} label="Yearly Income"
              value={stats ? money(stats.yearly_income) : "-"} tone="indigo" />
        <Stat icon={<Wallet className="w-5 h-5" />} label="Paid Amount"
              value={stats ? money(stats.paid_amount) : "-"} tone="emerald" />
        <Stat icon={<HandCoins className="w-5 h-5" />} label="Pending Payment"
              value={stats ? money(stats.pending_amount) : "-"} tone="amber" />
      </div>

      {stats && (stats.by_status?.length > 0 || stats.income_trend?.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card title="Payment Status Analysis">
            {stats.by_status?.length ? (
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={stats.by_status} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80}
                       label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(1)}%`}>
                    {stats.by_status.map((status) => (
                      <Cell key={status.name} fill={STATUS_COLOR[status.name] || "#94a3b8"} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ borderRadius: '8px', color: '#0f172a' }} itemStyle={{ color: '#0f172a' }} /><Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : <Empty text="No invoices yet." />}
          </Card>
          <Card title="Billed vs Collected">
            {stats.income_trend?.length ? (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={stats.income_trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#64748b" }} />
                  <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
                  <Tooltip contentStyle={{ borderRadius: '8px', color: '#0f172a' }} itemStyle={{ color: '#0f172a' }} /><Legend />
                  <Bar dataKey="billed" fill="#0d9488" radius={[4, 4, 0, 0]} name="Billed" />
                  <Bar dataKey="collected" fill="#10b981" radius={[4, 4, 0, 0]} name="Collected" />
                </BarChart>
              </ResponsiveContainer>
            ) : <Empty text="No income history yet." />}
          </Card>
        </div>
      )}

      {/* Invoice records */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
          <h3 className="font-semibold text-slate-800">Invoice Records</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase text-slate-500 bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-4 py-3">Invoice</th>
                <th className="px-4 py-3">Customer</th>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3 text-right">Amount</th>
                <th className="px-4 py-3 text-right">Paid</th>
                <th className="px-4 py-3 text-right">Balance</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-500">Loading...</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-500">No invoices created yet.</td></tr>
              ) : rows.map((i) => (
                <tr key={i.id} className="hover:bg-slate-50/60">
                  <td className="px-4 py-3 font-medium text-slate-900">{i.invoice_number}</td>
                  <td className="px-4 py-3 text-slate-600">{i.customer_name || "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{fmtDate(i.invoice_date)}</td>
                  <td className="px-4 py-3 text-right">{Number(i.total_price).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right text-emerald-600">{Number(i.paid_amount).toLocaleString()}</td>
                  <td className={`px-4 py-3 text-right font-medium ${i.balance > 0 ? "text-amber-600" : "text-slate-400"}`}>
                    {Number(i.balance).toLocaleString()}
                  </td>
                  <td className="px-4 py-3"><Pill value={i.payment_status} /></td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {i.balance > 0 && (
                      <Button size="sm" variant="outline" className="mr-1" onClick={() => setPayFor(i)}>
                        Pay
                      </Button>
                    )}
                    <button onClick={() => printInvoice(i)} className="text-slate-400 hover:text-teal-600 p-1.5" title="Print">
                      <Printer className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {showForm && (
        <InvoiceModal customers={customers} onClose={() => setShowForm(false)}
                      onSaved={() => { setShowForm(false); load(); }} />
      )}
      {payFor && (
        <PaymentModal invoice={payFor} onClose={() => setPayFor(null)}
                      onSaved={() => { setPayFor(null); load(); }} />
      )}
    </div>
  );
}

function InvoiceModal({ customers, onClose, onSaved }: {
  customers: CustomerOption[]; onClose: () => void; onSaved: () => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({
    invoice_number: "", invoice_date: today, customer_id: "", description: "",
    amount: "", discount: "0", due_date: "",
  });
  const [saving, setSaving] = useState(false);
  const total = Math.max(0, Number(form.amount || 0) - Number(form.discount || 0));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.invoice_number.trim() || Number(form.amount) <= 0) {
      Swal.fire({ icon: "warning", title: "Enter an invoice number and an amount above zero." }); return;
    }
    if (Number(form.discount) > Number(form.amount)) {
      Swal.fire({ icon: "warning", title: "Discount cannot exceed the amount." }); return;
    }
    setSaving(true);
    try {
      await api.post("/subplant/invoices", {
        ...form,
        customer_id: form.customer_id || null,
        amount: Number(form.amount), discount: Number(form.discount || 0),
        due_date: form.due_date || null,
      });
      Swal.fire({ icon: "success", title: "Invoice created" });
      onSaved();
    } catch (err: unknown) {
      Swal.fire({ icon: "error", title: "Error", text: getApiErrorMessage(err, "Save failed.") });
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <form onSubmit={submit} className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-lg p-6"
            onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Create Invoice</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Invoice Number *">
            <Input required value={form.invoice_number}
                   onChange={(e) => setForm({ ...form, invoice_number: e.target.value })} placeholder="INV-001" />
          </Field>
          <Field label="Date *">
            <Input type="date" required value={form.invoice_date}
                   onChange={(e) => setForm({ ...form, invoice_date: e.target.value })} />
          </Field>
          <Field label="Customer">
            <select className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm"
                    value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: e.target.value })}>
              <option value="">Select customer…</option>
              {customers.map((c) => <option key={c.id} value={c.id}>{c.customer_name}</option>)}
            </select>
          </Field>
          <Field label="Due Date">
            <Input type="date" value={form.due_date}
                   onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
          </Field>
          <Field label="Amount *">
            <Input type="number" min="0" step="0.01" required value={form.amount}
                   onChange={(e) => setForm({ ...form, amount: e.target.value })} placeholder="150000" />
          </Field>
          <Field label="Discount">
            <Input type="number" min="0" step="0.01" value={form.discount}
                   onChange={(e) => setForm({ ...form, discount: e.target.value })} placeholder="0" />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Description">
              <Input value={form.description}
                     onChange={(e) => setForm({ ...form, description: e.target.value })}
                     placeholder="e.g. August production" />
            </Field>
          </div>
        </div>

        <div className="bg-slate-50 border border-slate-100 rounded-lg p-3 text-sm text-slate-600 mt-4 flex justify-between">
          <span>Total price</span>
          <span className="font-semibold text-slate-900">{money(total)}</span>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving} className="bg-teal-600 hover:bg-teal-700">
            {saving ? "Saving..." : "Generate Invoice"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function PaymentModal({ invoice, onClose, onSaved }: {
  invoice: InvoiceRecord; onClose: () => void; onSaved: () => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [amount, setAmount] = useState(String(invoice.balance || ""));
  const [method, setMethod] = useState("Bank Transfer");
  const [payDate, setPayDate] = useState(today);
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const amt = Number(amount);
    if (amt <= 0) { Swal.fire({ icon: "warning", title: "Enter a payment amount." }); return; }
    if (amt > Number(invoice.balance) + 0.01) {
      Swal.fire({ icon: "warning", title: `Payment exceeds the balance of ${money(invoice.balance)}.` }); return;
    }
    setSaving(true);
    try {
      await api.post(`/subplant/invoices/${invoice.id}/payments`,
                     { amount: amt, method, payment_date: payDate });
      Swal.fire({ icon: "success", title: "Payment recorded" });
      onSaved();
    } catch (err: unknown) {
      Swal.fire({ icon: "error", title: "Error", text: getApiErrorMessage(err, "Save failed.") });
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <form onSubmit={submit} className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-md p-6"
            onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-slate-800 mb-1">Record Payment</h3>
        <p className="text-sm text-slate-500 mb-4">
          {invoice.invoice_number} · balance <strong>{money(invoice.balance)}</strong>
        </p>
        <div className="space-y-4">
          <Field label="Amount *">
            <Input type="number" min="0" step="0.01" required value={amount}
                   onChange={(e) => setAmount(e.target.value)} />
          </Field>
          <Field label="Payment Date">
            <Input type="date" value={payDate} onChange={(e) => setPayDate(e.target.value)} />
          </Field>
          <Field label="Method">
            <select className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm"
                    value={method} onChange={(e) => setMethod(e.target.value)}>
              {["Bank Transfer", "Cash", "Cheque", "Card"].map((m) => <option key={m}>{m}</option>)}
            </select>
          </Field>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving} className="bg-teal-600 hover:bg-teal-700">
            {saving ? "Saving..." : "Record Payment"}
          </Button>
        </div>
      </form>
    </div>
  );
}
