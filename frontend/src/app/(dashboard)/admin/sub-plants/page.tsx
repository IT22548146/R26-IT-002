"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Building2, Plus, ExternalLink, Factory, Mail, Info, TrendingUp } from "lucide-react";

const PORTAL_URL = process.env.NEXT_PUBLIC_SUBPLANT_PORTAL_URL || "http://localhost:3001";

export default function SubPlantsPage() {
  const router = useRouter();
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get("/admin/sub-plants");
      setRows(res.data);
    } catch (err) {
      console.error("Failed to load sub plants", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-6 text-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center">
            <Building2 className="w-6 h-6 mr-2 text-violet-600" /> Local Sub Plants
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            External production partners who record their own operations in the Sub Plant Portal.
          </p>
        </div>
        <Button onClick={() => setShowForm(true)} className="bg-violet-600 hover:bg-violet-700">
          <Plus className="w-4 h-4 mr-1" /> Register Sub Plant
        </Button>
      </div>

      <div className="rounded-lg border border-violet-200 bg-violet-50 px-4 py-3 text-sm text-violet-900 flex items-start gap-2">
        <Info className="w-4 h-4 mt-0.5 shrink-0" />
        <span>
          Registering a sub plant creates its portal login. The plant signs in at{" "}
          <a href={PORTAL_URL} target="_blank" rel="noreferrer" className="underline font-medium">
            {PORTAL_URL}
          </a>{" "}
          and records customers, orders, gatepasses and invoices. Their gatepass output flows into
          Plant Analytics, so they are scored alongside your own plants — but they are excluded from
          bulk-order allocation.
        </span>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
          <h3 className="font-semibold text-slate-800">Registered Sub Plants</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase text-slate-500 bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-4 py-3">Plant</th>
                <th className="px-4 py-3">Location</th>
                <th className="px-4 py-3 text-right">Machines</th>
                <th className="px-4 py-3 text-right">Employees</th>
                <th className="px-4 py-3">Portal Login</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">Loading...</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                  No sub plants registered yet.
                </td></tr>
              ) : rows.map((p) => (
                <tr key={p.id} className="hover:bg-slate-50/60">
                  <td className="px-4 py-3">
                    <p className="font-semibold text-slate-900 flex items-center gap-1.5">
                      <Factory className="w-3.5 h-3.5 text-violet-500" /> {p.name}
                    </p>
                    <p className="text-xs text-slate-400">{p.id}</p>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{p.location || "—"}</td>
                  <td className="px-4 py-3 text-right">{p.total_machines}</td>
                  <td className="px-4 py-3 text-right">{p.employee_count}</td>
                  <td className="px-4 py-3">
                    {p.portal_email ? (
                      <span className="text-slate-700 inline-flex items-center gap-1.5 text-xs">
                        <Mail className="w-3.5 h-3.5 text-slate-400" /> {p.portal_email}
                      </span>
                    ) : (
                      <span className="text-xs text-amber-600">No portal login</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button size="sm" variant="ghost" onClick={() => router.push("/admin/analytics")}>
                      <TrendingUp className="w-4 h-4 mr-1" /> Performance
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {showForm && (
        <SubPlantModal onClose={() => setShowForm(false)} onSaved={() => { setShowForm(false); load(); }} />
      )}
    </div>
  );
}

function SubPlantModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    plant_id: "", name: "", location: "", total_machines: "12", employee_count: "35",
    contact_no: "", full_name: "", email: "", password: "",
  });
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.plant_id.trim() || !form.name.trim()) {
      Swal.fire({ icon: "warning", title: "Plant ID and name are required." });
      return;
    }
    if (!form.email.trim() || form.password.length < 8) {
      Swal.fire({ icon: "warning", title: "Enter a portal email and a password of at least 8 characters." });
      return;
    }
    // Component 4 was trained on plants of a certain size; warn outside that band.
    const m = Number(form.total_machines), e2 = Number(form.employee_count);
    if (m < 8 || m > 22 || e2 < 28 || e2 > 68) {
      const r = await Swal.fire({
        icon: "warning",
        title: "Outside the scoring range",
        text: "Performance scoring works best with 8–22 machines and 28–68 employees. Register anyway?",
        showCancelButton: true, confirmButtonText: "Register anyway",
      });
      if (!r.isConfirmed) return;
    }

    setSaving(true);
    try {
      await api.post("/admin/sub-plants", {
        ...form,
        total_machines: Number(form.total_machines),
        employee_count: Number(form.employee_count),
      });
      Swal.fire({
        icon: "success",
        title: "Sub plant registered",
        text: `${form.email} can now sign in to the Sub Plant Portal.`,
      });
      onSaved();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Registration failed." });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <form onSubmit={submit}
            className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto text-slate-900"
            onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-slate-800 mb-1">Register Local Sub Plant</h3>
        <p className="text-sm text-slate-500 mb-5">
          Creates the plant and its portal login in one step.
        </p>

        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Plant details</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Plant ID *">
            <Input required value={form.plant_id}
                   onChange={(e) => setForm({ ...form, plant_id: e.target.value.toUpperCase() })}
                   placeholder="SP02" />
          </Field>
          <Field label="Plant Name *">
            <Input required value={form.name}
                   onChange={(e) => setForm({ ...form, name: e.target.value })}
                   placeholder="Lanka Mount Castle (Pvt) Ltd" />
          </Field>
          <Field label="Location">
            <Input value={form.location}
                   onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="Gampaha" />
          </Field>
          <Field label="Contact Number">
            <Input value={form.contact_no}
                   onChange={(e) => setForm({ ...form, contact_no: e.target.value })} placeholder="+94 11 234 5678" />
          </Field>
          <Field label="Total Machines">
            <Input type="number" min="1" value={form.total_machines}
                   onChange={(e) => setForm({ ...form, total_machines: e.target.value })} />
          </Field>
          <Field label="Employees">
            <Input type="number" min="1" value={form.employee_count}
                   onChange={(e) => setForm({ ...form, employee_count: e.target.value })} />
          </Field>
        </div>

        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 mt-6 mb-2">Portal login</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Contact Person">
            <Input value={form.full_name}
                   onChange={(e) => setForm({ ...form, full_name: e.target.value })} placeholder="Defaults to plant name" />
          </Field>
          <Field label="Email *">
            <Input type="email" required value={form.email}
                   onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="plant@subplant.com" />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Temporary Password *">
              <Input type="password" required minLength={8} value={form.password}
                     onChange={(e) => setForm({ ...form, password: e.target.value })}
                     placeholder="At least 8 characters" />
            </Field>
          </div>
        </div>

        <div className="bg-slate-50 border border-slate-100 rounded-lg p-3 text-xs text-slate-500 mt-4">
          The sub plant is scored in Plant Analytics from the gatepasses it records, but is
          excluded from bulk-order plant allocation.
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving} className="bg-violet-600 hover:bg-violet-700">
            {saving ? "Registering..." : "Register Sub Plant"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
      {children}
    </div>
  );
}
