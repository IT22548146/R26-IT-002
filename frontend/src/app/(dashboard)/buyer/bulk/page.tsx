"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Package, Plus, Sparkles, FileText, Search, Pencil, Trash2 } from "lucide-react";
import OrderTracker from "@/components/OrderTracker";
import StyleAutocomplete from "@/components/StyleAutocomplete";

// <input type="date"> needs YYYY-MM-DD; the API returns HTTP-date strings like
// "Mon, 31 Aug 2026 00:00:00 GMT", so normalise before prefilling the edit form.
const toDateInput = (s?: string) => {
  if (!s) return "";
  const d = new Date(s);
  return isNaN(d.getTime()) ? "" : d.toISOString().slice(0, 10);
};

export default function BuyerBulkOrders() {
  const searchParams = useSearchParams();
  const [orders, setOrders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(!!searchParams.get("new"));
  const [submitting, setSubmitting] = useState(false);

  const [formData, setFormData] = useState({
    style_number: "",
    bulk_order_quantity: "",
    style_priority: "Normal",
    bulk_order_approved_date: "",
    buyer_required_date: "",
    notes: "",
    // Specs auto-filled from the style catalog (read-only, display only)
    design_width: "",
    design_length: "",
    color_count: "",
    stitch_count: "",
  });

  const [availableStyles, setAvailableStyles] = useState<any[]>([]);
  const [specsLocked, setSpecsLocked] = useState(false);
  // Set when a preset style is not in the catalog - the buyer fills the specs in.
  const [specsManual, setSpecsManual] = useState(false);
  const [styleResetKey, setStyleResetKey] = useState(0);
  const [styleFile, setStyleFile] = useState<File | null>(null);
  const [viewingPdfId, setViewingPdfId] = useState<number | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [editing, setEditing] = useState<any | null>(null);
  const [editForm, setEditForm] = useState({ bulk_order_quantity: "", style_priority: "Normal", buyer_required_date: "", notes: "" });
  const [savingEdit, setSavingEdit] = useState(false);
  const [extOrder, setExtOrder] = useState<any | null>(null);
  const [extForm, setExtForm] = useState({ extension_days: "", message: "" });
  const [respondingId, setRespondingId] = useState<number | null>(null);

  // Today's date (YYYY-MM-DD) — blocks past required dates.
  const today = new Date().toISOString().split("T")[0];

  const fetchOrders = async () => {
    try {
      const res = await api.get("/buyer/orders/bulk");
      setOrders(res.data);
    } catch (err) {
      console.error("Failed to fetch bulk orders", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchStyles = async () => {
    try {
      const res = await api.get("/styles");
      setAvailableStyles(res.data);
    } catch (err) {
      console.error("Failed to fetch styles", err);
    }
  };

  useEffect(() => {
    fetchOrders();
    fetchStyles();
  }, []);

  // Arriving from a completed sample order (?style=XYZ) - preselect that style
  // once the catalog has loaded, so the buyer does not have to find it again.
  const presetStyle = searchParams.get("style");
  useEffect(() => {
    if (!presetStyle) return;
    const num = presetStyle.toUpperCase();
    const match = availableStyles.find(
      (s: any) => (s.style_number || "").toUpperCase() === num
    );
    if (match) {
      handleStyleSelect(match);
      return;
    }
    // A style created with a sample order stays 'Pending' until reviewed, so it is
    // not in the approved catalog yet. Fetch it directly so the specs still fill in
    // and the order can be submitted.
    api.get(`/styles/${encodeURIComponent(num)}`)
      .then((r) => { setSpecsManual(false); handleStyleSelect(r.data); })
      .catch(() => {
        // Legacy sample styles were free text and may not exist in the catalog.
        // Keep the number and let the buyer type the specs rather than blocking them.
        setFormData((f) => ({ ...f, style_number: num }));
        setSpecsManual(true);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetStyle, availableStyles]);

  // Picking a style fills the read-only specs; clearing it unlocks them.
  const handleStyleSelect = (style: any | null) => {
    if (style) {
      setSpecsManual(false);
      setFormData({
        ...formData,
        style_number: style.style_number,
        design_width: style.design_width?.toString() || "",
        design_length: style.design_length?.toString() || "",
        color_count: style.color_count?.toString() || "",
        stitch_count: style.stitch_count?.toString() || "",
      });
      setSpecsLocked(true);
    } else {
      setFormData({ ...formData, style_number: "", design_width: "", design_length: "", color_count: "", stitch_count: "" });
      setSpecsLocked(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.style_number.trim()) {
      Swal.fire({ icon: 'warning', title: 'Please select a style number.' });
      return;
    }
    if (!specsLocked && !specsManual) {
      Swal.fire({ icon: 'warning', title: 'Select a style from the list', text: 'Technical specs are filled in automatically from the catalog.' });
      return;
    }
    if (specsManual) {
      const missing = [
        ["design width", formData.design_width],
        ["design length", formData.design_length],
        ["colours", formData.color_count],
        ["stitch count", formData.stitch_count],
      ].filter(([, v]) => !String(v).trim() || Number(v) <= 0).map(([k]) => k);
      if (missing.length) {
        Swal.fire({ icon: 'warning', title: 'Technical specs required', text: `Enter a value for: ${missing.join(", ")}.` });
        return;
      }
    }
    if (Number(formData.bulk_order_quantity) <= 0) {
      Swal.fire({ icon: 'warning', title: 'Enter a valid total quantity.' });
      return;
    }
    if (formData.buyer_required_date < today) {
      Swal.fire({ icon: 'warning', title: 'Required date cannot be in the past.' });
      return;
    }
    if (styleFile && !styleFile.name.toLowerCase().endsWith(".pdf")) {
      Swal.fire({ icon: 'warning', title: 'Style file must be a PDF.' });
      return;
    }

    setSubmitting(true);
    const payload = new FormData();
    payload.append("style_number", formData.style_number);
    payload.append("style_priority", formData.style_priority);
    payload.append("buyer_required_date", formData.buyer_required_date);
    payload.append("bulk_order_quantity", String(Number(formData.bulk_order_quantity)));
    payload.append("design_width", String(Number(formData.design_width)));
    payload.append("design_length", String(Number(formData.design_length)));
    payload.append("color_count", String(Number(formData.color_count)));
    payload.append("stitch_count", String(Number(formData.stitch_count)));
    payload.append("notes", formData.notes);
    // Approved date is set to today automatically; daily commitment is derived server-side.
    payload.append("bulk_order_approved_date", today);
    if (styleFile) payload.append("style_pdf", styleFile);

    try {
      await api.post("/buyer/orders/bulk", payload);
      Swal.fire({ icon: 'success', title: "Bulk order submitted!" });
      setShowForm(false);
      setSpecsLocked(false);
      setSpecsManual(false);
      setStyleFile(null);
      setStyleResetKey((k) => k + 1);
      setFormData({ style_number: "", bulk_order_quantity: "", style_priority: "Normal", bulk_order_approved_date: "", buyer_required_date: "", notes: "", design_width: "", design_length: "", color_count: "", stitch_count: "" });
      fetchOrders();
    } catch (err: any) {
      Swal.fire({ icon: 'error', title: 'Error', text: err.response?.data?.error || "Failed to submit bulk order." });
    } finally {
      setSubmitting(false);
    }
  };

  const filteredOrders = orders.filter((order) => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return true;
    const label = order.status === "CustomerPending" ? "awaiting your approval" : order.status;
    return [order.style_number, order.status, label, order.style_priority, order.production_stage]
      .some((f) => (f ?? "").toString().toLowerCase().includes(term));
  });

  const openEdit = (order: any) => {
    setEditing(order);
    setEditForm({
      bulk_order_quantity: String(order.bulk_order_quantity ?? ""),
      style_priority: order.style_priority ?? "Normal",
      buyer_required_date: toDateInput(order.buyer_required_date),
      notes: order.notes ?? "",
    });
  };

  const handleEditSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (Number(editForm.bulk_order_quantity) <= 0) {
      Swal.fire({ icon: "warning", title: "Enter a valid total quantity." });
      return;
    }
    if (editForm.buyer_required_date < today) {
      Swal.fire({ icon: "warning", title: "Required date cannot be in the past." });
      return;
    }
    setSavingEdit(true);
    try {
      await api.put(`/buyer/orders/bulk/${editing.id}`, {
        bulk_order_quantity: Number(editForm.bulk_order_quantity),
        style_priority: editForm.style_priority,
        buyer_required_date: editForm.buyer_required_date,
        notes: editForm.notes,
      });
      Swal.fire({ icon: "success", title: "Order updated" });
      setEditing(null);
      fetchOrders();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Update failed." });
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDelete = async (order: any) => {
    const res = await Swal.fire({
      icon: "warning", title: "Delete this bulk order?",
      text: `Style ${order.style_number} — this cannot be undone.`,
      showCancelButton: true, confirmButtonText: "Delete", confirmButtonColor: "#dc2626",
    });
    if (!res.isConfirmed) return;
    try {
      await api.delete(`/buyer/orders/bulk/${order.id}`);
      Swal.fire({ icon: "success", title: "Order deleted" });
      fetchOrders();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Delete failed." });
    }
  };

  const handleApproveTimeline = async (order: any) => {
    const ok = await Swal.fire({
      title: "Approve this order?", text: "We'll proceed with the proposed timeline.",
      icon: "question", showCancelButton: true, confirmButtonText: "Approve",
    });
    if (!ok.isConfirmed) return;
    setRespondingId(order.id);
    try {
      await api.post(`/buyer/orders/bulk/${order.id}/respond`, { response: "Approved" });
      Swal.fire({ icon: "success", title: "Approved", text: "Thanks! The order will move into production." });
      fetchOrders();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to respond." });
    } finally {
      setRespondingId(null);
    }
  };

  const handleRequestExtension = async (e: React.FormEvent) => {
    e.preventDefault();
    setRespondingId(extOrder.id);
    try {
      await api.post(`/buyer/orders/bulk/${extOrder.id}/respond`, {
        response: "Rejected",
        extension_days: extForm.extension_days ? Number(extForm.extension_days) : undefined,
        message: extForm.message,
      });
      Swal.fire({ icon: "success", title: "Response sent", text: "We've let the team know." });
      setExtOrder(null);
      setExtForm({ extension_days: "", message: "" });
      fetchOrders();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to respond." });
    } finally {
      setRespondingId(null);
    }
  };

  const handleViewPdf = async (orderId: number) => {
    setViewingPdfId(orderId);
    try {
      const res = await api.get(`/buyer/orders/bulk/${orderId}/pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      window.open(url, "_blank", "noopener,noreferrer");
      setTimeout(() => window.URL.revokeObjectURL(url), 60_000);
    } catch {
      Swal.fire({ icon: "error", title: "Error", text: "Failed to load the style PDF." });
    } finally {
      setViewingPdfId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <Package className="w-6 h-6 mr-2 text-indigo-600" />
          My Bulk Orders
        </h2>
        <Button onClick={() => setShowForm(!showForm)} className="bg-indigo-600 hover:bg-indigo-700">
          {showForm ? "Cancel" : <><Plus className="w-4 h-4 mr-1" /> New Bulk Order</>}
        </Button>
      </div>

      {showForm && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-6 animate-in fade-in slide-in-from-top-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-slate-800">Place Bulk Order</h3>
            <span className="text-xs font-medium bg-blue-50 text-blue-600 px-3 py-1 rounded-full flex items-center">
              <Sparkles className="w-3 h-3 mr-1" /> Specs auto-fill from the style catalog
            </span>
          </div>
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Core Details */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="md:col-span-1">
                <label className="block text-sm font-medium text-slate-700 mb-1">Style Number *</label>
                <StyleAutocomplete styles={availableStyles} resetKey={styleResetKey} presetValue={presetStyle ? presetStyle.toUpperCase() : ""} onSelect={handleStyleSelect} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Total Quantity *</label>
                <Input type="number" min="1" required value={formData.bulk_order_quantity} onChange={e => setFormData({...formData, bulk_order_quantity: e.target.value})} placeholder="e.g. 10000" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Required Date *</label>
                <Input type="date" required min={today} value={formData.buyer_required_date} onChange={e => setFormData({...formData, buyer_required_date: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Priority</label>
                <select
                  className="flex h-10 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-950"
                  value={formData.style_priority}
                  onChange={e => setFormData({...formData, style_priority: e.target.value})}
                >
                  <option>Low</option>
                  <option>Normal</option>
                  <option>High</option>
                  <option>No Urgency</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Notes</label>
              <Input value={formData.notes} onChange={e => setFormData({ ...formData, notes: e.target.value })} placeholder="Optional details for this order..." />
            </div>

            {/* Technical Specs — read-only, auto-filled from the selected style */}
            <div className="pt-4 border-t border-slate-100">
              <h4 className="text-sm font-medium text-slate-700 mb-1">Technical Specs</h4>
              <p className="text-xs text-slate-400 mb-3">
                {specsManual
                  ? "This style is not in the catalog yet — enter its specs below."
                  : "Read-only — filled automatically from the style catalog."}
              </p>
              {specsManual ? (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Design Width (cm) *</label>
                    <Input type="number" step="0.1" min="0" value={formData.design_width}
                           onChange={e => setFormData({ ...formData, design_width: e.target.value })} />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Design Length (cm) *</label>
                    <Input type="number" step="0.1" min="0" value={formData.design_length}
                           onChange={e => setFormData({ ...formData, design_length: e.target.value })} />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Colours *</label>
                    <Input type="number" min="1" value={formData.color_count}
                           onChange={e => setFormData({ ...formData, color_count: e.target.value })} />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Stitch Count *</label>
                    <Input type="number" min="1" value={formData.stitch_count}
                           onChange={e => setFormData({ ...formData, stitch_count: e.target.value })} />
                  </div>
                </div>
              ) : specsLocked ? (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <SpecTile label="Design Width" value={`${formData.design_width} cm`} />
                  <SpecTile label="Design Length" value={`${formData.design_length} cm`} />
                  <SpecTile label="Colours" value={formData.color_count} />
                  <SpecTile label="Stitch Count" value={formData.stitch_count} />
                </div>
              ) : (
                <div className="text-sm text-slate-400 bg-slate-50 border border-dashed border-slate-200 rounded-lg px-4 py-3">
                  Select a style number above to load its technical specs.
                </div>
              )}
            </div>

            {/* Optional style PDF */}
            <div className="pt-4 border-t border-slate-100">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Style PDF <span className="text-slate-400 font-normal">(optional)</span>
              </label>
              <Input
                type="file"
                accept="application/pdf,.pdf"
                onChange={(e) => setStyleFile(e.target.files?.[0] ?? null)}
                className="file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1 file:text-sm file:text-slate-700 hover:file:bg-slate-200 cursor-pointer py-1.5"
              />
              {styleFile && <p className="mt-1 text-xs text-slate-500 truncate">Selected: {styleFile.name}</p>}
            </div>

            <div className="pt-4 flex justify-end">
              <Button type="submit" className="bg-indigo-600 hover:bg-indigo-700" disabled={submitting}>
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
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by style, status, priority..."
            className="pl-9"
          />
        </div>
      )}

      {loading ? (
        <div>Loading...</div>
      ) : orders.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
          <p className="text-slate-500">You haven't placed any bulk orders yet.</p>
        </div>
      ) : filteredOrders.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
          <p className="text-slate-500">No bulk orders match your search.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredOrders.map((order) => (
            <div key={order.id} className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden p-6">
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center space-x-3 mb-2">
                    <span className="text-lg font-bold text-slate-900">Style: {order.style_number}</span>
                    <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      order.status === 'Pending' ? 'bg-amber-100 text-amber-800' :
                      order.status === 'CustomerPending' ? 'bg-purple-100 text-purple-800' :
                      order.status === 'Processing' ? 'bg-blue-100 text-blue-800' :
                      order.status === 'Hold' ? 'bg-orange-100 text-orange-800' :
                      order.status === 'Completed' ? 'bg-green-100 text-green-800' :
                      order.status === 'Shipped' ? 'bg-slate-200 text-slate-600' :
                      'bg-slate-100 text-slate-800'
                    }`}>
                      {order.status === 'CustomerPending' ? 'Awaiting Your Approval' : order.status}
                    </span>
                  </div>
                  <p className="text-sm text-slate-500">
                    Total Qty: <span className="font-medium text-slate-700">{order.bulk_order_quantity}</span> |
                    Req Date: <span className="font-medium text-slate-700">{order.buyer_required_date}</span>
                  </p>
                  {order.notes && (
                    <p className="text-sm text-slate-500 mt-1 italic border-l-2 border-indigo-200 pl-2">"{order.notes}"</p>
                  )}
                </div>
                {order.style_pdf_path && (
                  <Button variant="outline" onClick={() => handleViewPdf(order.id)} disabled={viewingPdfId === order.id}>
                    <FileText className="w-4 h-4 mr-1" />
                    {viewingPdfId === order.id ? "Opening..." : "View PDF"}
                  </Button>
                )}
              </div>

              {/* Order tracking */}
              <div className="mt-5 pt-5 border-t border-slate-100">
                <OrderTracker type="bulk" order={order} tone="indigo" />
              </div>

              {/* Timeline reply — buyer approves or requests more time */}
              {order.status === "CustomerPending" && order.customer_response !== "Approved" && (
                <div className="mt-4 rounded-lg border border-purple-200 bg-purple-50 p-4">
                  <p className="text-sm text-purple-900 font-medium mb-3">
                    We've proposed a completion timeline for this order. How would you like to proceed?
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button className="bg-green-600 hover:bg-green-700" disabled={respondingId === order.id}
                      onClick={() => handleApproveTimeline(order)}>
                      Approve & Proceed
                    </Button>
                    <Button variant="outline" disabled={respondingId === order.id}
                      onClick={() => { setExtOrder(order); setExtForm({ extension_days: "", message: "" }); }}>
                      Request More Time
                    </Button>
                  </div>
                </div>
              )}

              {/* Buyer's recorded reply */}
              {order.customer_response && (
                <div className="mt-3 text-sm text-slate-500">
                  Your reply: <span className={`font-medium ${order.customer_response === "Approved" ? "text-green-600" : "text-orange-600"}`}>
                    {order.customer_response === "Approved" ? "Approved" : "Requested changes"}
                  </span>
                  {order.extension_days_requested ? ` · requested +${order.extension_days_requested} day(s)` : ""}
                  {order.customer_message ? ` · "${order.customer_message}"` : ""}
                </div>
              )}

              {/* Show AI Feedback */}
              {order.c2_result && (
                <div className="mt-4 bg-slate-50 p-4 rounded-lg text-sm border border-slate-100">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-slate-500">AI Plant Allocation Recommendation</p>
                    <span className={`font-semibold ${order.c2_result.allocation_strategy === 'Single Plant' ? 'text-blue-600' : 'text-purple-600'}`}>
                      {order.c2_result.allocation_strategy}
                    </span>
                  </div>
                  <ul className="space-y-1">
                    {order.c2_result.allocation?.map((alloc: any, idx: number) => (
                       <li key={idx} className="flex justify-between text-slate-700 bg-white px-3 py-1 rounded border border-slate-200">
                         <span>{alloc.role}: <strong>{alloc.plant}</strong></span>
                         <span>{alloc.assigned_qty} units</span>
                       </li>
                    ))}
                  </ul>
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

      {/* Request-more-time modal */}
      {extOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={() => setExtOrder(null)}>
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-slate-800 mb-1">Request More Time — {extOrder.style_number}</h3>
            <p className="text-sm text-slate-500 mb-4">Tell the team how many extra days you can allow, and add a note if you like.</p>
            <form onSubmit={handleRequestExtension} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Extra days you can allow</label>
                <Input type="number" min="1" value={extForm.extension_days}
                  onChange={(e) => setExtForm({ ...extForm, extension_days: e.target.value })} placeholder="e.g. 13" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Message (optional)</label>
                <Input value={extForm.message} onChange={(e) => setExtForm({ ...extForm, message: e.target.value })} placeholder="Any details for the team..." />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button type="button" variant="outline" onClick={() => setExtOrder(null)}>Cancel</Button>
                <Button type="submit" disabled={respondingId === extOrder.id} className="bg-indigo-600 hover:bg-indigo-700">Send Response</Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit modal */}
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={() => setEditing(null)}>
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-slate-800 mb-4">Edit Bulk Order — {editing.style_number}</h3>
            <form onSubmit={handleEditSave} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Total Quantity *</label>
                <Input type="number" min="1" required value={editForm.bulk_order_quantity}
                  onChange={(e) => setEditForm({ ...editForm, bulk_order_quantity: e.target.value })} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Required Date *</label>
                <Input type="date" required min={today} value={editForm.buyer_required_date}
                  onChange={(e) => setEditForm({ ...editForm, buyer_required_date: e.target.value })} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Priority</label>
                <select value={editForm.style_priority} onChange={(e) => setEditForm({ ...editForm, style_priority: e.target.value })}
                  className="flex h-10 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-950">
                  <option>Low</option><option>Normal</option><option>High</option><option>No Urgency</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Notes</label>
                <Input value={editForm.notes} onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })} placeholder="Optional details..." />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button type="button" variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
                <Button type="submit" disabled={savingEdit} className="bg-indigo-600 hover:bg-indigo-700">{savingEdit ? "Saving..." : "Save Changes"}</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function SpecTile({ label, value }: { label: string; value: any }) {
  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-3">
      <p className="text-xs text-slate-400 uppercase tracking-wide mb-1">{label}</p>
      <p className="text-sm font-semibold text-slate-800">{value || "—"}</p>
    </div>
  );
}
