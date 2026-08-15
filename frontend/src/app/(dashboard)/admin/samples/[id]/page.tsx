"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import OrderTracker, { StageSelect } from "@/components/OrderTracker";
import {
  ArrowLeft, Factory, CheckCircle2, AlertCircle, TrendingUp, MapPin, Download,
  Mail, Clock, CalendarCheck, Info,
} from "lucide-react";

const actionPill = (a?: string) =>
  a === "Approved" ? "bg-green-100 text-green-700"
    : a === "Rejected" ? "bg-orange-100 text-orange-700"
    : "bg-slate-100 text-slate-600";

const fmtDate = (s?: string) => {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d.getTime()) ? String(s) : d.toLocaleDateString();
};
const fmtDateTime = (s?: string) => {
  if (!s) return "";
  const d = new Date(s);
  return isNaN(d.getTime()) ? String(s) : d.toLocaleString();
};
const toDateInput = (s?: string) => {
  if (!s) return "";
  const d = new Date(s);
  return isNaN(d.getTime()) ? "" : d.toISOString().slice(0, 10);
};

export default function SampleOrderDetail() {
  const { id } = useParams();
  const router = useRouter();
  const [order, setOrder] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selectedPlant, setSelectedPlant] = useState("");
  const [assigning, setAssigning] = useState(false);
  const [requestOpen, setRequestOpen] = useState(false);
  const [applyOpen, setApplyOpen] = useState(false);

  const fetchOrder = async () => {
    try {
      const res = await api.get(`/admin/orders/sample/${id}`);
      setOrder(res.data);
    } catch (err) {
      console.error("Failed to fetch sample order", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (id) fetchOrder();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handleStageChange = async (stage: string) => {
    try {
      await api.post(`/admin/orders/sample/${id}/stage`, { stage });
      Swal.fire({ icon: "success", title: `Stage updated to ${stage}` });
      await fetchOrder();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to update stage." });
    }
  };

  const handleAssign = async () => {
    if (!selectedPlant) {
      Swal.fire({ icon: "info", title: "Select a factory to assign." });
      return;
    }
    setAssigning(true);
    try {
      await api.post(`/admin/orders/sample/${id}/assign`, { plant_id: selectedPlant });
      Swal.fire({ icon: "success", title: "Factory assigned — order is now Processing." });
      await fetchOrder();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to assign." });
    } finally {
      setAssigning(false);
    }
  };

  const handleResponse = async (response: "Approved" | "Rejected") => {
    try {
      await api.post(`/admin/orders/sample/${id}/customer-response`, { response });
      Swal.fire({ icon: "success", title: `Recorded: ${response}` });
      await fetchOrder();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed." });
    }
  };

  const downloadPdf = async () => {
    try {
      const res = await api.get(`/admin/orders/sample/${id}/pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `${order.style_number}_style.pdf`; a.click();
      setTimeout(() => window.URL.revokeObjectURL(url), 10_000);
    } catch {
      Swal.fire({ icon: "error", title: "Error", text: "Failed to download the style PDF." });
    }
  };

  if (loading) return <div className="p-8 text-slate-500">Loading details...</div>;
  if (!order) return <div className="p-8 text-red-500">Sample order not found</div>;

  const c1 = order.c1_result;
  const isFeasible = order.feasibility
    ? order.feasibility === "Feasible"
    : c1?.planning_output?.feasible;
  const allPlants = c1?.model2_plant_selection?.all_scores || [];

  // Date-negotiation sub-state (status stays 'Pending' throughout).
  const awaiting = Boolean(order.timeline_email_sent_at) && !order.customer_response;
  const agreed = order.customer_response === "Approved";
  const declined = order.customer_response === "Rejected";
  const hasNegotiation = Boolean(order.timeline_email_sent_at) || (order.replies?.length > 0);
  const canAssign = order.status === "Pending" && isFeasible;
  const assigned = Boolean(order.assigned_plant_name);

  return (
    <div className="space-y-6 animate-in fade-in duration-500 text-slate-900">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => router.back()}>
          <ArrowLeft className="w-5 h-5" />
        </Button>
        <div className="min-w-0">
          <h2 className="text-2xl font-bold text-slate-900 tracking-tight">
            Sample Order #{order.id}
          </h2>
          <p className="text-sm text-slate-500">
            Style: {order.style_number} · Buyer: {order.buyer_name}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {order.style_pdf_path && (
            <Button variant="outline" size="sm" onClick={downloadPdf}>
              <Download className="w-4 h-4 mr-1" /> Style PDF
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: summary */}
        <div className="lg:col-span-1 space-y-6 lg:sticky lg:top-6 lg:self-start">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
              <h3 className="font-semibold text-slate-800">Order Summary</h3>
            </div>
            <div className="p-6 space-y-4 text-sm">
              <Row label="Buyer" value={order.buyer_name} />
              <Row label="Artwork" value={order.artwork_number || "—"} />
              <Row label="Sample Qty" value={order.sample_qty} />
              <Row label="Receive Date" value={fmtDate(order.receive_date)} />
              <Row label="Required Date" value={fmtDate(order.buyer_required_date)} />
              <div className="flex justify-between items-center">
                <span className="text-slate-500">Status</span>
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                  order.status === "Pending" ? "bg-amber-50 text-amber-700 border-amber-200"
                    : order.status === "Processing" ? "bg-blue-50 text-blue-700 border-blue-200"
                    : order.status === "Completed" ? "bg-green-50 text-green-700 border-green-200"
                    : "bg-slate-50 text-slate-700 border-slate-200"}`}>
                  {order.status}
                </span>
              </div>
              {order.feasibility && (
                <div className="flex justify-between items-center">
                  <span className="text-slate-500">Feasibility</span>
                  <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                    isFeasible ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                               : "bg-red-50 text-red-700 border-red-200"}`}>
                    {order.feasibility}
                  </span>
                </div>
              )}
              {order.notes && (
                <div>
                  <p className="text-slate-500 mb-1">Notes</p>
                  <p className="text-slate-900">{order.notes}</p>
                </div>
              )}
            </div>
          </div>

          {/* Assigned factory */}
          {assigned && (
            <div className="bg-white rounded-xl border-2 border-emerald-300 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-emerald-100 bg-emerald-50 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <h3 className="font-semibold text-emerald-900">Assigned Factory</h3>
              </div>
              <div className="p-6">
                <p className="font-bold text-slate-900 flex items-center gap-2">
                  <Factory className="w-4 h-4 text-emerald-600" /> {order.assigned_plant_name}
                </p>
                {order.assigned_plant_location && (
                  <p className="text-xs text-slate-500 mt-1 flex items-center gap-1">
                    <MapPin className="w-3 h-3" /> {order.assigned_plant_location}
                  </p>
                )}
                {order.assigned_at && (
                  <p className="text-xs text-slate-400 mt-2">Assigned {fmtDateTime(order.assigned_at)}</p>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right: actions + AI + negotiation */}
        <div className="lg:col-span-2 space-y-6">
          {/* Tracking + actions */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50 flex items-center justify-between gap-3">
              <h3 className="font-semibold text-slate-800">Order Actions</h3>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500 hidden sm:inline">Production stage</span>
                <StageSelect value={order.production_stage} onChange={handleStageChange} />
              </div>
            </div>
            <div className="p-6 space-y-5">
              <OrderTracker type="sample" order={order} tone="blue" />

              <div className="flex flex-wrap gap-2 items-center pt-1">
                {canAssign && (
                  <div className="flex items-center gap-2 bg-slate-50 p-1.5 rounded-lg border border-slate-200">
                    <select
                      className="text-sm border border-slate-300 rounded-md py-1.5 px-2 bg-white"
                      value={selectedPlant}
                      onChange={(e) => setSelectedPlant(e.target.value)}
                    >
                      <option value="">Select factory…</option>
                      {allPlants.map((p: any) => (
                        <option key={p.plant} value={p.plant}>#{p.rank} — {p.plant}</option>
                      ))}
                    </select>
                    <Button size="sm" onClick={handleAssign} disabled={assigning}
                            className="bg-emerald-600 hover:bg-emerald-700">
                      {assigning ? "Assigning..." : "Assign Factory"}
                    </Button>
                  </div>
                )}

                {order.status === "Pending" && !isFeasible && !awaiting && !agreed && (
                  <Button variant="outline" size="sm" onClick={() => setRequestOpen(true)}>
                    <Mail className="w-4 h-4 mr-1" /> {declined ? "Request Another Date" : "Request New Date"}
                  </Button>
                )}
                {order.status === "Pending" && awaiting && (
                  <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-purple-50 text-purple-700 border border-purple-200">
                    <Clock className="w-3.5 h-3.5" /> Awaiting customer reply
                  </span>
                )}
                {order.status === "Pending" && agreed && (
                  <Button size="sm" onClick={() => setApplyOpen(true)} className="bg-emerald-600 hover:bg-emerald-700">
                    <CalendarCheck className="w-4 h-4 mr-1" /> Apply New Date &amp; Re-check
                  </Button>
                )}
                {order.status === "Processing" && (
                  <span className="text-sm text-slate-500">In production — advance the stage above as work progresses.</span>
                )}
              </div>
            </div>
          </div>

          {/* Date negotiation */}
          {hasNegotiation && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-100 bg-slate-50 flex items-center gap-2">
                <Mail className="w-4 h-4 text-purple-600" />
                <h3 className="font-semibold text-slate-800">Receive-Date Negotiation</h3>
              </div>
              <div className="p-6 space-y-3 text-sm">
                {order.timeline_email_sent_at && (
                  <p className="text-slate-600">
                    Requested a new receive date
                    {order.proposed_receive_date ? <> — proposed <strong>{fmtDate(order.proposed_receive_date)}</strong></> : ""}
                    <span className="text-slate-400"> ({fmtDateTime(order.timeline_email_sent_at)})</span>
                  </p>
                )}
                {order.customer_response && (
                  <div className="rounded-lg border border-slate-200 bg-white p-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${actionPill(order.customer_response)}`}>
                        {order.customer_response}
                      </span>
                      {order.extension_days_requested ? (
                        <span className="text-xs font-medium text-purple-700">+{order.extension_days_requested} day(s)</span>
                      ) : null}
                      {order.customer_responded_at && (
                        <span className="text-xs text-slate-400">{fmtDateTime(order.customer_responded_at)}</span>
                      )}
                    </div>
                    {order.customer_message && (
                      <p className="mt-2 text-slate-700 whitespace-pre-line">&ldquo;{order.customer_message}&rdquo;</p>
                    )}
                  </div>
                )}
                {awaiting && (
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-slate-500">No email reply yet — record it manually:</span>
                    <Button size="sm" variant="outline" onClick={() => handleResponse("Approved")}>Mark Agreed</Button>
                    <Button size="sm" variant="ghost" onClick={() => handleResponse("Rejected")}>Mark Declined</Button>
                  </div>
                )}
                {order.replies?.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                      Email replies ({order.replies.length})
                    </p>
                    {order.replies.map((m: any) => (
                      <div key={m.id} className="rounded-lg border border-slate-200 bg-white p-3">
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <span className="text-xs font-medium text-slate-700">{m.from_addr}</span>
                          <div className="flex items-center gap-1.5">
                            {m.detected_action && (
                              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${actionPill(m.detected_action)}`}>
                                {m.detected_action}{m.extension_days ? ` · +${m.extension_days}d` : ""}
                              </span>
                            )}
                            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                              m.applied ? "bg-blue-100 text-blue-700" : "bg-amber-100 text-amber-700"}`}>
                              {m.applied ? "Applied" : "Needs review"}
                            </span>
                          </div>
                        </div>
                        {m.body && <p className="mt-1.5 text-slate-600 whitespace-pre-line">{m.body}</p>}
                        {m.note && <p className="mt-1 text-xs text-slate-400">{m.note}</p>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* AI Component 1 */}
          {c1 ? (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Tile tone={isFeasible ? "emerald" : "red"} label="Feasibility"
                      value={isFeasible ? "Feasible" : "Infeasible"}
                      icon={isFeasible ? <CheckCircle2 className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />} />
                <Tile tone="amber" label="Overrun Prediction"
                      value={c1.model1_overrun?.interpretation?.replace("N/A - ", "") || "N/A"}
                      icon={<TrendingUp className="w-5 h-5" />} small />
                <Tile tone="blue" label="Risk Level"
                      value={c1.planning_output?.risk_level || "N/A"}
                      icon={<AlertCircle className="w-5 h-5" />} />
              </div>

              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
                  <h3 className="font-semibold text-slate-800">Scheduling Logic</h3>
                </div>
                <div className="p-6 grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                  <Row label="Buyer Required Date" value={fmtDate(c1.scheduling?.buyer_required_date)} />
                  <Row label="Est. Completion Date" value={fmtDate(c1.scheduling?.estimated_completion_date)} />
                  <Row label="Buffer Days" value={`${c1.input_summary?.buffer_days ?? "—"} days`} />
                  <Row label="Overtime Probability"
                       value={c1.model3_factory_overtime?.overtime_probability != null
                         ? `${(c1.model3_factory_overtime.overtime_probability * 100).toFixed(1)}%` : "N/A"} />
                </div>
              </div>

              {c1.planning_output?.risk_summary && (
                <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                  <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
                    <h3 className="font-semibold text-slate-800">AI Recommendation Summary</h3>
                  </div>
                  <ul className="p-6 space-y-2.5">
                    {c1.planning_output.risk_summary.split("|").map((item: string, idx: number) => {
                      const t = item.trim();
                      if (!t) return null;
                      return (
                        <li key={idx} className="flex items-start text-sm text-slate-700 leading-relaxed">
                          <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 mt-1.5 mr-2.5 shrink-0" />
                          <span className="capitalize">{t}</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}

              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
                  <h3 className="font-semibold text-slate-800">AI Factory Suitability Ranking</h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="text-xs uppercase text-slate-500 bg-slate-50 border-b border-slate-200">
                      <tr>
                        <th className="px-4 py-3">Rank</th>
                        <th className="px-4 py-3">Factory</th>
                        <th className="px-4 py-3 text-right">Match Score</th>
                        <th className="px-4 py-3 text-right">Available Cap</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {allPlants.map((p: any) => {
                        const isAssigned = order.assigned_plant_name === p.plant;
                        return (
                          <tr key={p.plant} className={isAssigned ? "bg-emerald-50" : "hover:bg-slate-50/60"}>
                            <td className="px-4 py-3">
                              <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold ${
                                isAssigned ? "bg-emerald-600 text-white"
                                  : p.rank === 1 ? "bg-blue-600 text-white" : "bg-slate-200 text-slate-700"}`}>
                                {p.rank}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className={`font-semibold ${isAssigned ? "text-emerald-900" : "text-slate-900"}`}>
                                  {p.plant}
                                </span>
                                {isAssigned && (
                                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-600 text-white">
                                    ASSIGNED
                                  </span>
                                )}
                              </div>
                              <p className="text-xs text-slate-500 flex items-center gap-1 mt-0.5">
                                <MapPin className="w-3 h-3" /> {p.location}
                              </p>
                            </td>
                            <td className="px-4 py-3 text-right tabular-nums">
                              {(p.composite_score * 100).toFixed(1)}
                              <span className="text-xs text-slate-400"> / 100</span>
                            </td>
                            <td className="px-4 py-3 text-right font-medium text-emerald-700">
                              {(p.live_free_ratio * 100).toFixed(0)}% free
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : (
            <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
              <Info className="w-6 h-6 text-slate-400 mx-auto mb-2" />
              <p className="text-slate-500">No AI Component 1 analysis available for this order.</p>
            </div>
          )}
        </div>
      </div>

      {requestOpen && (
        <RequestDateModal order={order} onClose={() => setRequestOpen(false)}
                          onSent={() => { setRequestOpen(false); fetchOrder(); }} />
      )}
      {applyOpen && (
        <ApplyDateModal order={order} onClose={() => setApplyOpen(false)}
                        onApplied={() => { setApplyOpen(false); fetchOrder(); }} />
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: any }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-slate-500 shrink-0">{label}</span>
      <span className="font-medium text-slate-900 text-right">{value ?? "—"}</span>
    </div>
  );
}

function Tile({ icon, label, value, tone, small }: {
  icon: React.ReactNode; label: string; value: string; tone: string; small?: boolean;
}) {
  const tones: Record<string, string> = {
    emerald: "bg-emerald-50 text-emerald-600",
    red: "bg-red-50 text-red-600",
    amber: "bg-amber-50 text-amber-600",
    blue: "bg-blue-50 text-blue-600",
  };
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center mb-3 ${tones[tone]}`}>{icon}</div>
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</p>
      <p className={`font-bold text-slate-900 mt-1 ${small ? "text-sm leading-snug" : "text-lg"}`}>{value}</p>
    </div>
  );
}

function RequestDateModal({ order, onClose, onSent }: { order: any; onClose: () => void; onSent: () => void }) {
  const [proposedDate, setProposedDate] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);

  const send = async () => {
    setSending(true);
    try {
      await api.post(`/admin/orders/sample/${order.id}/request-date`, {
        proposed_date: proposedDate || undefined,
        message: message || undefined,
      });
      Swal.fire({
        icon: "success", title: "Date-request email sent",
        text: "The buyer has been asked to confirm a new receive date.",
      });
      onSent();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to send." });
    } finally { setSending(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-lg p-6 text-slate-900"
           onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-slate-800 mb-1">Request a New Receive Date</h3>
        <p className="text-sm text-slate-500 mb-4">
          Style {order.style_number} · {order.buyer_name} · current target{" "}
          <strong>{fmtDate(order.receive_date)}</strong>
        </p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Proposed new receive date <span className="text-slate-400 font-normal">(optional)</span>
            </label>
            <Input type="date" value={proposedDate} onChange={(e) => setProposedDate(e.target.value)} />
            <p className="mt-1 text-xs text-slate-400">Leave blank to ask the buyer to suggest a date.</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Message <span className="text-slate-400 font-normal">(optional)</span>
            </label>
            <textarea rows={3} value={message} onChange={(e) => setMessage(e.target.value)}
                      placeholder="Add any context for the buyer…"
                      className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-950" />
          </div>
        </div>
        <div className="bg-slate-50 border border-slate-100 rounded-lg p-3 text-xs text-slate-500 my-4">
          The buyer receives an email tagged <strong>[Sample #{order.id}]</strong>. Their reply is folded
          back onto this order by &ldquo;Check Email Replies&rdquo;.
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={send} disabled={sending} className="bg-blue-600 hover:bg-blue-700">
            {sending ? "Sending..." : "Send Request"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function ApplyDateModal({ order, onClose, onApplied }: { order: any; onClose: () => void; onApplied: () => void }) {
  const [newDate, setNewDate] = useState(toDateInput(order.proposed_receive_date));
  const [saving, setSaving] = useState(false);

  const apply = async () => {
    if (!newDate) {
      Swal.fire({ icon: "warning", title: "Pick the agreed receive date." });
      return;
    }
    setSaving(true);
    try {
      const res = await api.post(`/admin/orders/sample/${order.id}/apply-new-date`, { new_date: newDate });
      Swal.fire({
        icon: res.data.feasible ? "success" : "warning",
        title: "New date applied",
        text: `Receive date set to ${res.data.receive_date} — now ${res.data.feasibility}.`,
      });
      onApplied();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to apply new date." });
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-md p-6 text-slate-900"
           onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-slate-800 mb-1">Apply New Receive Date</h3>
        <p className="text-sm text-slate-500 mb-4">Style {order.style_number} · {order.buyer_name}</p>
        <label className="block text-sm font-medium text-slate-700 mb-1">Agreed receive date</label>
        <Input type="date" value={newDate} onChange={(e) => setNewDate(e.target.value)} />
        {order.customer_message && (
          <p className="mt-2 text-xs text-slate-500">Buyer said: &ldquo;{order.customer_message}&rdquo;</p>
        )}
        <div className="bg-slate-50 border border-slate-100 rounded-lg p-3 text-xs text-slate-500 my-4">
          Feasibility is recalculated for the new date. If it becomes feasible, you can assign a factory.
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={apply} disabled={saving} className="bg-emerald-600 hover:bg-emerald-700">
            {saving ? "Applying..." : "Apply & Re-check"}
          </Button>
        </div>
      </div>
    </div>
  );
}
