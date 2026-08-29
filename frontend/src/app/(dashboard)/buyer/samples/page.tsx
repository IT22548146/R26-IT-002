"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import api from "@/lib/api";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ClipboardList, Plus, Search, FileText, Pencil, Trash2, ChevronDown, ChevronUp, Package } from "lucide-react";
import OrderTracker from "@/components/OrderTracker";

// <input type="date"> needs YYYY-MM-DD; the API returns HTTP-date strings like
// "Sat, 22 Aug 2026 00:00:00 GMT", so normalise before prefilling the edit form.
const toDateInput = (s?: string) => {
  if (!s) return "";
  const d = new Date(s);
  return isNaN(d.getTime()) ? "" : d.toISOString().slice(0, 10);
};

export default function BuyerSamples() {
  const searchParams = useSearchParams();
  const [orders, setOrders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(!!searchParams.get("new"));
  const [submitting, setSubmitting] = useState(false);

  // Form State
  // A sample order is always for a NEW style, so the style is created here and
  // submitted with the order (no picking from the existing catalog).
  const [formData, setFormData] = useState({
    style_number: "",
    style_name: "",
    garment_type: "",
    design_width: "",
    design_length: "",
    color_count: "",
    stitch_count: "",
    complexity: "Medium",
    description: "",
    artwork_number: "",
    sample_qty: "",
    receive_date: "",
    buyer_required_date: "",
    notes: ""
  });

  const [styleFile, setStyleFile] = useState<File | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [viewingPdfId, setViewingPdfId] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [editing, setEditing] = useState<any | null>(null);
  const [editForm, setEditForm] = useState({ sample_qty: "", buyer_required_date: "", notes: "" });
  const [savingEdit, setSavingEdit] = useState(false);

  // Today's date (YYYY-MM-DD) — used to block past required dates.
  const today = new Date().toISOString().split("T")[0];
  // Orders need a realistic lead time - the buyer cannot request a date sooner
  // than this. Mirrors MIN_LEAD_DAYS on the server.
  const MIN_LEAD_DAYS = 20;
  const earliestDate = new Date(Date.now() + MIN_LEAD_DAYS * 86400000)
    .toISOString().split("T")[0];

  const fetchOrders = async () => {
    try {
      const res = await api.get("/buyer/orders/sample");
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

  const handleViewPdf = async (orderId: number) => {
    setViewingPdfId(orderId);
    try {
      const res = await api.get(`/buyer/orders/sample/${orderId}/pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      window.open(url, "_blank", "noopener,noreferrer");
      // Revoke after giving the new tab time to load it.
      setTimeout(() => window.URL.revokeObjectURL(url), 60_000);
    } catch (err: any) {
      Swal.fire({ icon: 'error', title: 'Error', text: "Failed to load the style PDF." });
    } finally {
      setViewingPdfId(null);
    }
  };

  const openEdit = (order: any) => {
    setEditing(order);
    setEditForm({
      sample_qty: String(order.sample_qty ?? ""),
      buyer_required_date: toDateInput(order.buyer_required_date),
      notes: order.notes ?? "",
    });
  };

  const handleEditSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const qty = parseInt(editForm.sample_qty, 10);
    if (isNaN(qty) || qty < 5 || qty > 9) {
      Swal.fire({ icon: 'warning', title: 'Sample quantity must be between 5 and 9.' });
      return;
    }
    if (editForm.buyer_required_date < earliestDate) {
      Swal.fire({ icon: 'warning', title: `Required date must be at least ${MIN_LEAD_DAYS} days from today.` });
      return;
    }
    setSavingEdit(true);
    try {
      await api.put(`/buyer/orders/sample/${editing.id}`, {
        sample_qty: qty,
        buyer_required_date: editForm.buyer_required_date,
        notes: editForm.notes,
      });
      Swal.fire({ icon: 'success', title: 'Order updated' });
      setEditing(null);
      fetchOrders();
    } catch (err: any) {
      Swal.fire({ icon: 'error', title: 'Error', text: err.response?.data?.error || "Update failed." });
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDelete = async (order: any) => {
    const res = await Swal.fire({
      icon: 'warning', title: 'Delete this sample order?',
      text: `Style ${order.style_number} — this cannot be undone.`,
      showCancelButton: true, confirmButtonText: 'Delete', confirmButtonColor: '#dc2626',
    });
    if (!res.isConfirmed) return;
    try {
      await api.delete(`/buyer/orders/sample/${order.id}`);
      Swal.fire({ icon: 'success', title: 'Order deleted' });
      fetchOrders();
    } catch (err: any) {
      Swal.fire({ icon: 'error', title: 'Error', text: err.response?.data?.error || "Delete failed." });
    }
  };

  const statusPill = (status: string) => {
    const map: Record<string, string> = {
      Pending: 'bg-amber-100 text-amber-800',
      Processing: 'bg-blue-100 text-blue-800',
      Completed: 'bg-green-100 text-green-800',
      Cancelled: 'bg-slate-200 text-slate-600',
    };
    return map[status] || 'bg-slate-100 text-slate-800';
  };

  const filteredOrders = orders.filter((order) => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return true;
    return [order.style_number, order.artwork_number, order.status, order.assigned_plant_name]
      .some((field) => (field ?? "").toString().toLowerCase().includes(term));
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validate sample quantity (5–9 inclusive).
    const qty = parseInt(formData.sample_qty, 10);
    if (isNaN(qty) || qty < 5 || qty > 9) {
      Swal.fire({ icon: 'warning', title: 'Invalid quantity', text: 'Sample quantity must be between 5 and 9.' });
      return;
    }

    // Validate the required date is not in the past.
    if (!formData.style_number.trim()) {
      Swal.fire({ icon: 'warning', title: 'Style number is required.' });
      return;
    }
    if (!styleFile) {
      Swal.fire({ icon: 'warning', title: 'A style PDF is required for a new style.' });
      return;
    }
    if (!styleFile.name.toLowerCase().endsWith(".pdf")) {
      Swal.fire({ icon: 'warning', title: 'The style file must be a PDF.' });
      return;
    }
    if (formData.buyer_required_date < earliestDate) {
      Swal.fire({ icon: 'warning', title: 'Invalid date', text: `Required date must be at least ${MIN_LEAD_DAYS} days from today (earliest ${earliestDate}).` });
      return;
    }

    setSubmitting(true);
    try {
      // Step 1 - register the new style (PDF is mandatory here).
      const styleNumber = formData.style_number.trim().toUpperCase();
      const stylePayload = new FormData();
      ([["style_number", styleNumber],
        ["style_name", formData.style_name],
        ["garment_type", formData.garment_type],
        ["design_width", formData.design_width],
        ["design_length", formData.design_length],
        ["color_count", formData.color_count],
        ["stitch_count", formData.stitch_count],
        ["complexity", formData.complexity],
        ["description", formData.description]] as [string, string][])
        .forEach(([k, v]: [string, string]) => stylePayload.append(k, v));
      stylePayload.append("style_pdf", styleFile as File);
      await api.post("/buyer/styles", stylePayload);

      // Step 2 - raise the sample order against the style just created.
      const payload = new FormData();
      payload.append("style_number", styleNumber);
      payload.append("artwork_number", formData.artwork_number);
      payload.append("sample_qty", String(qty));
      payload.append("notes", formData.notes);
      payload.append("buyer_required_date", formData.buyer_required_date);
      payload.append("receive_date", today); // auto-set today
      if (styleFile) payload.append("style_pdf", styleFile);

      await api.post("/buyer/orders/sample", payload);
      Swal.fire({ icon: 'success', title: "Sample order submitted successfully! AI analysis complete." });
      setShowForm(false);
      setFormData({
        style_number: "", style_name: "", garment_type: "", design_width: "",
        design_length: "", color_count: "", stitch_count: "", complexity: "Medium",
        description: "", artwork_number: "", sample_qty: "",
        receive_date: "", buyer_required_date: "", notes: ""
      });
      setStyleFile(null);
      fetchOrders();
    } catch (err: any) {
      Swal.fire({ icon: 'error', title: 'Error', text: err.response?.data?.error || "Failed to submit order." });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <ClipboardList className="w-6 h-6 mr-2 text-blue-600" />
          My Sample Orders
        </h2>
        <Button onClick={() => setShowForm(!showForm)}>
          {showForm ? "Cancel" : <><Plus className="w-4 h-4 mr-1" /> New Sample Request</>}
        </Button>
      </div>

      {showForm && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-6 animate-in fade-in slide-in-from-top-4">
          <h3 className="text-lg font-semibold text-slate-800 mb-1">Request New Sample</h3>
          <p className="text-sm text-slate-500 mb-4">
            Every sample is for a new style, so enter the style details here — the style is
            registered automatically with your request.
          </p>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Style Number *</label>
                <Input required value={formData.style_number}
                       onChange={e => setFormData({ ...formData, style_number: e.target.value })}
                       placeholder="e.g. USAC-002001" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Artwork Number *</label>
                <Input required value={formData.artwork_number} onChange={e => setFormData({...formData, artwork_number: e.target.value})} placeholder="e.g. ART-001" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Style Name</label>
                <Input value={formData.style_name} onChange={e => setFormData({...formData, style_name: e.target.value})} placeholder="e.g. Classic Tee" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Garment Type</label>
                <Input value={formData.garment_type} onChange={e => setFormData({...formData, garment_type: e.target.value})} placeholder="e.g. T-Shirt" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Design Width (cm) *</label>
                <Input type="number" step="0.1" required value={formData.design_width} onChange={e => setFormData({...formData, design_width: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Design Length (cm) *</label>
                <Input type="number" step="0.1" required value={formData.design_length} onChange={e => setFormData({...formData, design_length: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Colours *</label>
                <Input type="number" min="1" required value={formData.color_count} onChange={e => setFormData({...formData, color_count: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Stitch Count *</label>
                <Input type="number" min="1" required value={formData.stitch_count} onChange={e => setFormData({...formData, stitch_count: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Complexity</label>
                <select value={formData.complexity} onChange={e => setFormData({...formData, complexity: e.target.value})}
                        className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-950">
                  {["Low", "Medium", "High", "Hard"].map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Description</label>
                <Input value={formData.description} onChange={e => setFormData({...formData, description: e.target.value})} placeholder="Optional details..." />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Sample Quantity * <span className="text-slate-400 font-normal">(5–9)</span></label>
                <Input type="number" min="5" max="9" required value={formData.sample_qty} onChange={e => setFormData({...formData, sample_qty: e.target.value})} placeholder="5" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Notes</label>
                <Input value={formData.notes} onChange={e => setFormData({...formData, notes: e.target.value})} placeholder="Optional details..." />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Required Date *</label>
                <Input type="date" required min={earliestDate} value={formData.buyer_required_date} onChange={e => setFormData({...formData, buyer_required_date: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Style PDF *</label>
                <Input
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={e => setStyleFile(e.target.files?.[0] ?? null)}
                  className="file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1 file:text-sm file:text-slate-700 hover:file:bg-slate-200 cursor-pointer py-1.5"
                />
                {styleFile && <p className="mt-1 text-xs text-slate-500 truncate">Selected: {styleFile.name}</p>}
              </div>
            </div>
            <div className="pt-4 flex justify-end">
              <Button type="submit" disabled={submitting}>
                {submitting ? "Submitting..." : "Submit"}
              </Button>
            </div>
          </form>
        </div>
      )}

      {!loading && orders.length > 0 && (
        <div className="relative max-w-sm">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <Input
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            placeholder="Search by style, artwork, status, plant..."
            className="pl-9"
          />
        </div>
      )}

      {loading ? (
        <div>Loading...</div>
      ) : orders.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
          <p className="text-slate-500">You haven't requested any samples yet.</p>
        </div>
      ) : filteredOrders.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
          <p className="text-slate-500">No sample orders match your search.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredOrders.map((order) => (
            <div key={order.id} className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden p-6">
              <div className="flex justify-between items-start gap-3">
                <div className="min-w-0">
                  <div className="flex items-center space-x-3 mb-2">
                    <span className="text-lg font-bold text-slate-900">Style: {order.style_number}</span>
                    <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${statusPill(order.status)}`}>
                      {order.status}
                    </span>
                  </div>
                  <p className="text-sm text-slate-500">
                    Artwork: {order.artwork_number || '—'} | Qty: {order.sample_qty} | Req Date: {order.buyer_required_date}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {order.style_pdf_path && (
                    <Button variant="outline" onClick={() => handleViewPdf(order.id)} disabled={viewingPdfId === order.id}>
                      <FileText className="w-4 h-4 mr-1" />
                      {viewingPdfId === order.id ? "Opening..." : "View PDF"}
                    </Button>
                  )}
                  <Button variant="ghost" onClick={() => setExpandedId(expandedId === order.id ? null : order.id)}>
                    {expandedId === order.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    <span className="ml-1">Details</span>
                  </Button>
                </div>
              </div>

              {/* Order tracking */}
              <div className="mt-5 pt-5 border-t border-slate-100">
                <OrderTracker type="sample" order={order} tone="blue" />
              </div>

              {/* Detail view */}
              {expandedId === order.id && (
                <div className="mt-4 bg-slate-50 rounded-lg border border-slate-100 p-4 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
                  <Detail label="Placed on" value={order.created_at?.split('T')[0]?.split(' ')[0]} />
                  <Detail label="Current status" value={order.status} />
                  <Detail label="Sample quantity" value={order.sample_qty} />
                  <Detail label="Required date" value={order.buyer_required_date} />
                  <Detail label="Artwork number" value={order.artwork_number || '—'} />
                  <Detail label="Assigned plant" value={order.assigned_plant_name || '—'} />
                  <div className="sm:col-span-2"><Detail label="Notes" value={order.notes || '—'} /></div>
                </div>
              )}

              {/* Sample finished - the next step is a bulk order for the same style.
                  status and production_stage are tracked separately, so treat either
                  "Completed" or a stage of "Delivery" as done. */}
              {(order.status === 'Completed' || order.production_stage === 'Delivery') && (
                <div className="mt-4 border-t border-slate-100 pt-4 flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm text-slate-600">
                    Sample complete — ready to order this style in bulk?
                  </p>
                  <Link href={`/buyer/bulk?new=1&style=${encodeURIComponent(order.style_number)}`}>
                    <Button className="bg-indigo-600 hover:bg-indigo-700">
                      <Package className="w-4 h-4 mr-1" /> Create Bulk Order
                    </Button>
                  </Link>
                </div>
              )}

              {/* Buyer CRUD — only while Pending */}
              {order.status === 'Pending' && (
                <div className="mt-4 flex gap-2 border-t border-slate-100 pt-4">
                  <Button variant="outline" onClick={() => openEdit(order)}>
                    <Pencil className="w-4 h-4 mr-1" /> Edit
                  </Button>
                  <Button variant="danger" onClick={() => handleDelete(order)}>
                    <Trash2 className="w-4 h-4 mr-1" /> Delete
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Edit modal */}
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={() => setEditing(null)}>
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-slate-800 mb-4">Edit Sample Order — {editing.style_number}</h3>
            <form onSubmit={handleEditSave} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Sample Quantity * <span className="text-slate-400 font-normal">(5–9)</span></label>
                <Input type="number" min="5" max="9" required value={editForm.sample_qty}
                  onChange={(e) => setEditForm({ ...editForm, sample_qty: e.target.value })} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Required Date *</label>
                <Input type="date" required min={earliestDate} value={editForm.buyer_required_date}
                  onChange={(e) => setEditForm({ ...editForm, buyer_required_date: e.target.value })} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Notes</label>
                <Input value={editForm.notes} onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })} placeholder="Optional details..." />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button type="button" variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
                <Button type="submit" disabled={savingEdit}>{savingEdit ? "Saving..." : "Save Changes"}</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: any }) {
  return (
    <div>
      <span className="text-slate-400">{label}: </span>
      <span className="text-slate-800 font-medium">{value ?? '—'}</span>
    </div>
  );
}
