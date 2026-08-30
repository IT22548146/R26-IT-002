"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import api from "@/lib/api";
import Swal from "@/lib/swal";
import { ArrowLeft, CheckCircle2, AlertTriangle, AlertCircle, Info, Mail, RefreshCw, Factory, Pause, Play, Truck, Split, Plus, X, Clock, CalendarCheck } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { StageSelect } from "@/components/OrderTracker";

const replyPill = (r?: string) =>
  r === "Approved" ? "bg-green-100 text-green-700"
    : r === "Rejected" ? "bg-orange-100 text-orange-700"
    : "bg-slate-100 text-slate-600";

const fmtDateTime = (s?: string) => {
  if (!s) return "";
  const d = new Date(s);
  return isNaN(d.getTime()) ? String(s) : d.toLocaleString();
};

export default function BulkOrderDetail() {
  const { id } = useParams();
  const router = useRouter();
  const [order, setOrder] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reevaluating, setReevaluating] = useState(false);
  const [allPlants, setAllPlants] = useState<any[]>([]);
  const [assignOpen, setAssignOpen] = useState(false);
  const [emailOpen, setEmailOpen] = useState(false);

  const fetchOrder = async () => {
    try {
      const res = await api.get(`/admin/orders/bulk/${id}`);
      setOrder(res.data);
    } catch (err) {
      console.error("Failed to fetch order details", err);
    } finally {
      setLoading(false);
    }
  };

  const handleReevaluate = async () => {
    setReevaluating(true);
    try {
      const res = await api.post(`/admin/orders/bulk/${id}/reevaluate`);
      const { before, after } = res.data || {};
      const changes: string[] = [];
      if (before?.top_plant !== after?.top_plant) changes.push(`Top plant: ${before?.top_plant ?? "—"} → ${after?.top_plant ?? "—"}`);
      if (before?.deadline_match !== after?.deadline_match) changes.push(`Deadline: ${before?.deadline_match ?? "—"} → ${after?.deadline_match ?? "—"}`);
      if (before?.allocation_type !== after?.allocation_type) changes.push(`Strategy: ${before?.allocation_type ?? "—"} → ${after?.allocation_type ?? "—"}`);
      Swal.fire({
        icon: "success",
        title: "Re-evaluated with current capacity",
        text: changes.length ? changes.join(" · ") : "No change — the recommendation is still current.",
      });
      await fetchOrder();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to re-evaluate." });
    } finally {
      setReevaluating(false);
    }
  };

  const handleStageChange = async (stage: string) => {
    try {
      await api.post(`/admin/orders/bulk/${id}/stage`, { stage });
      Swal.fire({ icon: "success", title: `Stage updated to ${stage}` });
      await fetchOrder();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to update stage." });
    }
  };

  // These buttons RECORD a reply the buyer gave outside the app (phone, direct
  // email). They are not the admin approving on the buyer's behalf, so confirm
  // the intent explicitly before writing it against the buyer's name.
  const handleCustomerResponse = async (response: "Approved" | "Rejected") => {
    const proposed = order?.proposed_required_date;
    const confirm = await Swal.fire({
      icon: "warning",
      title: `Record that the buyer ${response.toLowerCase()} this?`,
      text: response === "Approved"
        ? (proposed
            ? `Only do this if the buyer confirmed outside the app. The required date will move to ${new Date(proposed).toLocaleDateString()}.`
            : "Only do this if the buyer confirmed outside the app.")
        : "Only do this if the buyer declined outside the app. The order moves to On Hold.",
      showCancelButton: true,
      confirmButtonText: `Yes, buyer ${response.toLowerCase()}`,
    });
    if (!confirm.isConfirmed) return;
    try {
      const res = await api.post(`/admin/orders/bulk/${id}/customer-response`, { response });
      Swal.fire({
        icon: "success",
        title: `Recorded: ${response}`,
        text: res.data.buyer_required_date
          ? `Required date updated to ${res.data.buyer_required_date}.`
          : (res.data.assignable ? "You can now assign a plant." : "Order moved to On Hold."),
      });
      await fetchOrder();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed." });
    }
  };

  // Accept the extension the buyer asked for: moves buyer_required_date out and
  // re-runs Component 2 against the new deadline.
  const handleAcceptExtension = async () => {
    const days = order?.extension_days_requested;
    const r = await Swal.fire({
      icon: "question",
      title: days ? `Accept +${days} day(s)?` : "Accept the new date?",
      text: "The required date moves out and the timeline is recalculated.",
      showCancelButton: true, confirmButtonText: "Accept",
    });
    if (!r.isConfirmed) return;
    try {
      const res = await api.post(`/admin/orders/bulk/${id}/apply-extension`, {});
      Swal.fire({
        icon: "success",
        title: "Required date updated",
        text: `${res.data.previous_required_date} → ${res.data.buyer_required_date}` +
              (res.data.deadline_match ? ` · deadline ${res.data.deadline_match}` : ""),
      });
      await fetchOrder();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to apply the extension." });
    }
  };

  const handleHold = async (hold: boolean) => {
    try {
      await api.post(`/admin/orders/bulk/${id}/hold`, { hold });
      await fetchOrder();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed." });
    }
  };

  const handleConfirmShipment = async () => {
    const r = await Swal.fire({ title: "Confirm shipment?", text: "This will email the buyer.", icon: "warning", showCancelButton: true, confirmButtonText: "Confirm" });
    if (!r.isConfirmed) return;
    try {
      await api.post(`/admin/orders/bulk/${id}/confirm-shipment`);
      Swal.fire({ icon: "success", title: "Shipment confirmed!" });
      await fetchOrder();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed." });
    }
  };

  useEffect(() => {
    if (id) fetchOrder();
    // Full plant list — fallback for the assign menu when there's no AI ranking.
    api.get("/admin/plants").then((r) => setAllPlants(r.data)).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (loading) {
    return <div className="p-8 text-slate-500">Loading details...</div>;
  }

  if (!order) {
    return <div className="p-8 text-red-500">Order not found</div>;
  }

  // A failed Component-2 run is stored as { error: "..." } — treat that (and any
  // result missing production_days) as "no usable AI data" rather than rendering blanks.
  const c2Error: string | undefined = order.c2_result?.error;
  const c2_result =
    order.c2_result && !c2Error && order.c2_result.production_days ? order.c2_result : null;
  const deadlineMatched = c2_result?.deadline?.deadline_match === "Match";
  const canReeval = ["Pending", "CustomerPending", "Hold"].includes(order.status);
  const canAssign = ["Pending", "CustomerPending", "Hold"].includes(order.status);
  const c2ok = Boolean(c2_result);
  // Timeline email sent but the buyer has not replied yet - assignment must wait.
  const awaitingBuyer = order.status === "CustomerPending" && !order.customer_response;
  const extensionRequested = order.customer_response === "Rejected" && Boolean(order.extension_days_requested);

  // Plants this order was actually assigned to (highlighted in the ranking below).
  const assignedPlants: any[] = order.allocations || [];
  const assignedNames = new Set(assignedPlants.map((a: any) => a.plant_name));

  // Assign-menu plants: full AI ranking (each with can_handle_solo), or all plants
  // as a fallback when there's no ranking.
  const assignablePlants = () => {
    const ranking = order.c2_result?.plant_recommendation?.ranking || [];
    if (ranking.length) return ranking;
    return allPlants.map((p: any) => ({ plant: p.name, score: null, fallback: true }));
  };
  const isFallbackPlants = () => !(order.c2_result?.plant_recommendation?.ranking?.length);
  const samplePlant = () => order.c2_result?.plant_recommendation?.sample_plant;

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex items-center gap-4 mb-6">
        <Button variant="ghost" size="sm" onClick={() => router.back()}>
          <ArrowLeft className="w-5 h-5" />
        </Button>
        <div>
          <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Bulk Order #{order.id} Details</h2>
          <p className="text-sm text-slate-500">Style: {order.style_number} | Priority: {order.style_priority}</p>
        </div>
        {canReeval && (
          <Button variant="outline" size="sm" className="ml-auto" onClick={handleReevaluate} disabled={reevaluating}>
            <RefreshCw className={`w-4 h-4 mr-1 ${reevaluating ? "animate-spin" : ""}`} />
            {reevaluating ? "Re-evaluating..." : "Re-evaluate with current capacity"}
          </Button>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Basic Order Info */}
        <div className="lg:col-span-1 space-y-6 lg:sticky lg:top-6 lg:self-start">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
              <h3 className="font-semibold text-slate-800">Order Summary</h3>
            </div>
            <div className="p-6 space-y-4 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-500">Buyer:</span>
                <span className="font-medium text-slate-900">{order.buyer_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Quantity:</span>
                <span className="font-medium text-slate-900">{order.bulk_order_quantity?.toLocaleString()} pcs</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Daily Commitment:</span>
                <span className="font-medium text-slate-900">{order.daily_commitment?.toLocaleString()} pcs/day</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Approved Date:</span>
                <span className="font-medium text-slate-900">{order.approved_date || order.bulk_order_approved_date}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Required Date:</span>
                <span className="font-medium text-slate-900">{order.buyer_required_date}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Status:</span>
                <span className="font-medium text-slate-900">{order.status}</span>
              </div>
            </div>
          </div>

          {/* Style Specs */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
              <h3 className="font-semibold text-slate-800">Technical Specs</h3>
            </div>
            <div className="p-6 grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-slate-500 text-xs">Width (in)</p>
                <p className="font-medium text-slate-900">{order.design_width}</p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Length (in)</p>
                <p className="font-medium text-slate-900">{order.design_length}</p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Color Count</p>
                <p className="font-medium text-slate-900">{order.color_count}</p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Stitch Count</p>
                <p className="font-medium text-slate-900">{order.stitch_count?.toLocaleString()}</p>
              </div>
            </div>
          </div>
        </div>

        {/* AI Details */}
        <div className="lg:col-span-2 space-y-6">

          {/* Order Actions — moved here from the list card */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50 flex items-center justify-between gap-3">
              <h3 className="font-semibold text-slate-800">Order Actions</h3>
              <div className="flex items-center gap-2">
                <StageSelect value={order.production_stage} onChange={handleStageChange} />
              </div>
            </div>
            <div className="p-6 flex flex-wrap gap-2 items-center">
              {order.status === "Pending" && c2ok && (
                <Button variant="outline" size="sm" onClick={() => setEmailOpen(true)}>
                  <Mail className="w-4 h-4 mr-1" /> Send Timeline Email
                </Button>
              )}

              {order.status === "CustomerPending" && order.customer_response !== "Approved" && (
                <div className="w-full rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs text-slate-500 mb-2">
                    Waiting for the buyer to respond in their portal. Only use these if they
                    replied <strong>outside the app</strong>:
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" className="border-green-300 text-green-700 hover:bg-green-50"
                            onClick={() => handleCustomerResponse("Approved")}>
                      Record buyer approval
                    </Button>
                    <Button size="sm" variant="outline" className="border-orange-300 text-orange-700 hover:bg-orange-50"
                            onClick={() => handleCustomerResponse("Rejected")}>
                      Record buyer rejection
                    </Button>
                  </div>
                </div>
              )}

              {awaitingBuyer && (
                <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-purple-50 text-purple-700 border border-purple-200">
                  <Clock className="w-3.5 h-3.5" /> Awaiting buyer reply — assignment locked
                </span>
              )}

              {extensionRequested && (
                <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700" onClick={handleAcceptExtension}>
                  <CalendarCheck className="w-4 h-4 mr-1" /> Accept +{order.extension_days_requested} day(s)
                </Button>
              )}

              {canAssign && (
                <Button size="sm" className="bg-indigo-600 hover:bg-indigo-700" onClick={() => setAssignOpen(true)}
                  title={awaitingBuyer ? "Waiting for the buyer to respond to the proposed timeline" : undefined}
                  disabled={order.status === "CustomerPending" && order.customer_response !== "Approved"}>
                  <Factory className="w-4 h-4 mr-1" /> Assign Plant
                </Button>
              )}

              {["Pending", "CustomerPending", "Processing"].includes(order.status) && (
                <Button size="sm" variant="ghost" onClick={() => handleHold(true)}>
                  <Pause className="w-4 h-4 mr-1" /> Hold
                </Button>
              )}
              {order.status === "Hold" && (
                <Button size="sm" variant="outline" onClick={() => handleHold(false)}>
                  <Play className="w-4 h-4 mr-1" /> Release
                </Button>
              )}

              {order.status === "Completed" && (
                <Button size="sm" className="bg-indigo-600 hover:bg-indigo-700" onClick={handleConfirmShipment}>
                  <Truck className="w-4 h-4 mr-1" /> Confirm Shipment
                </Button>
              )}

              {order.status === "Processing" && (
                <span className="text-sm text-slate-500">Assigned to production — advance the stage above as work progresses.</span>
              )}
              {order.status === "Shipped" && (
                <span className="text-sm text-slate-500">This order has shipped.</span>
              )}
            </div>
          </div>

          {/* Customer Communication — timeline email + captured replies */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50 flex items-center justify-between gap-2">
              <h3 className="font-semibold text-slate-800 flex items-center gap-2">
                <Mail className="w-4 h-4 text-indigo-600" /> Customer Communication
              </h3>
              {order.timeline_email_sent_at && (
                <span className="text-xs text-slate-400">Timeline email sent {fmtDateTime(order.timeline_email_sent_at)}</span>
              )}
            </div>
            <div className="p-6 space-y-4">
              {/* What we proposed - so the admin sees the same figures as the buyer. */}
              {order.timeline_decision && (
                <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-sm">
                  <p className="font-semibold text-indigo-900">
                    {order.timeline_decision === "cannot_complete"
                      ? `Proposed: ${order.timeline_gap_days} extra day(s)`
                      : "Proposed: can complete within the buyer's schedule"}
                  </p>
                  <p className="text-xs text-indigo-700 mt-1">
                    {order.timeline_needed_days} days needed vs {order.timeline_given_days} given
                    {order.proposed_required_date
                      ? ` · new date ${new Date(order.proposed_required_date).toLocaleDateString()} (pending acceptance)`
                      : ""}
                  </p>
                </div>
              )}

              {/* Latest structured response */}
              {order.customer_response ? (
                <div className="rounded-lg border border-slate-200 p-4">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${replyPill(order.customer_response)}`}>
                      {order.customer_response}
                    </span>
                    {order.extension_days_requested ? (
                      <span className="text-xs font-medium text-purple-700 bg-purple-50 border border-purple-200 rounded-full px-2 py-0.5">
                        +{order.extension_days_requested} day(s) requested
                      </span>
                    ) : null}
                    {order.customer_responded_at && (
                      <span className="text-xs text-slate-400">{fmtDateTime(order.customer_responded_at)}</span>
                    )}
                  </div>
                  {order.customer_message && (
                    <p className="mt-2 text-sm text-slate-700 whitespace-pre-line">&ldquo;{order.customer_message}&rdquo;</p>
                  )}
                </div>
              ) : order.timeline_email_sent_at ? (
                <p className="text-sm text-slate-500">Awaiting the customer&apos;s reply&hellip;</p>
              ) : null}

              {/* Raw inbound email replies */}
              {order.replies && order.replies.length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Email replies ({order.replies.length})
                  </h4>
                  {order.replies.map((m: any) => (
                    <div key={m.id} className="rounded-lg border border-slate-200 p-4">
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <span className="font-medium text-slate-800 text-sm">{m.from_addr}</span>
                        <div className="flex items-center gap-2">
                          {m.detected_action && (
                            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${replyPill(m.detected_action)}`}>
                              {m.detected_action}{m.extension_days ? ` · +${m.extension_days}d` : ""}
                            </span>
                          )}
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${m.applied ? "bg-blue-100 text-blue-700" : "bg-amber-100 text-amber-700"}`}>
                            {m.applied ? "Applied" : "Needs review"}
                          </span>
                        </div>
                      </div>
                      {m.subject && <p className="text-xs text-slate-400 mt-1">{m.subject}</p>}
                      {m.body && (
                        <p className="mt-2 text-sm text-slate-700 bg-slate-50 border border-slate-100 rounded-lg p-3 whitespace-pre-line">{m.body}</p>
                      )}
                      {m.note && <p className="mt-2 text-xs text-slate-400">{m.note}</p>}
                      <p className="mt-2 text-xs text-slate-400">{fmtDateTime(m.created_at)}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Empty state */}
              {!order.customer_response && !order.timeline_email_sent_at && (!order.replies || order.replies.length === 0) && (
                <p className="text-sm text-slate-500">
                  No customer communication yet. Use &ldquo;Send Timeline Email&rdquo; from the Bulk Orders list to start the conversation.
                </p>
              )}
            </div>
          </div>

          {c2_result ? (
            <>
              {/* Top Level Summary Cards */}
              <div className="grid grid-cols-3 gap-4">
                <div className={`p-4 rounded-xl border ${c2_result.capacity_status === 'OK' ? 'bg-green-50 border-green-200' : 'bg-amber-50 border-amber-200'}`}>
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Capacity Status</p>
                  <p className={`font-bold ${c2_result.capacity_status === 'OK' ? 'text-green-700' : 'text-amber-700'}`}>
                    {c2_result.capacity_status}
                  </p>
                </div>
                <div className={`p-4 rounded-xl border ${c2_result.deadline?.deadline_match === 'Match' ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Deadline Match</p>
                  <p className={`font-bold ${c2_result.deadline?.deadline_match === 'Match' ? 'text-green-700' : 'text-red-700'}`}>
                    {c2_result.deadline?.deadline_match}
                  </p>
                </div>
                <div className="p-4 rounded-xl border bg-blue-50 border-blue-200">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Complexity</p>
                  <p className="font-bold text-blue-700">
                    {c2_result.derived?.complexity}
                  </p>
                </div>
              </div>

              {/* Warnings and Notes */}
              {c2_result.warnings && c2_result.warnings.length > 0 && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-4">
                  <div className="flex items-center space-x-2 text-red-800 mb-2 font-semibold">
                    <AlertTriangle className="w-5 h-5" />
                    <span>AI Warnings</span>
                  </div>
                  <ul className="list-disc list-inside space-y-1 text-sm text-red-700">
                    {c2_result.warnings.map((warn: string, i: number) => (
                      <li key={i}>{warn}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Production Timeline */}
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
                  <h3 className="font-semibold text-slate-800">Production Timeline Estimation</h3>
                </div>
                <div className="p-6">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                    <div className="bg-slate-50 p-4 rounded-lg text-center">
                      <p className="text-slate-500 text-xs mb-1">Cutting</p>
                      <p className="font-semibold text-slate-800">{c2_result.production_days?.cutting_days?.toFixed(1)} days</p>
                    </div>
                    <div className="bg-slate-50 p-4 rounded-lg text-center">
                      <p className="text-slate-500 text-xs mb-1">Sewing</p>
                      <p className="font-semibold text-slate-800">{c2_result.production_days?.sewing_days?.toFixed(1)} days</p>
                    </div>
                    <div className="bg-slate-50 p-4 rounded-lg text-center border-2 border-indigo-100 bg-indigo-50/30">
                      <p className="text-indigo-600 text-xs font-medium mb-1">Embroidery (ML)</p>
                      <p className="font-bold text-indigo-900">{c2_result.production_days?.embroidery_days?.toFixed(1)} days</p>
                    </div>
                    <div className="bg-slate-50 p-4 rounded-lg text-center">
                      <p className="text-slate-500 text-xs mb-1">Shipment</p>
                      <p className="font-semibold text-slate-800">{c2_result.production_days?.shipment_days} days</p>
                    </div>
                  </div>
                  
                  <div className="flex justify-between items-center bg-slate-900 text-white p-4 rounded-lg">
                    <span className="font-medium">Total Predicted Lead Time</span>
                    <span className="text-xl font-bold">{c2_result.production_days?.total_lead_days?.toFixed(1)} days</span>
                  </div>
                  
                  {c2_result.production_days?.production_days_note && (
                    <div className="mt-4 p-3 bg-slate-50 rounded text-sm text-slate-600 flex space-x-2">
                      <Info className="w-5 h-5 flex-shrink-0 text-slate-400" />
                      <span>{c2_result.production_days.production_days_note}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Deadline Gap Analysis */}
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
                  <h3 className="font-semibold text-slate-800">Deadline Analysis</h3>
                </div>
                <div className="p-6">
                  <div className="grid grid-cols-2 gap-4 text-sm mb-4">
                    <div className="p-3 border rounded">
                      <p className="text-slate-500 mb-1">Days Available</p>
                      <p className="font-medium">{c2_result.deadline?.deadline_gap?.days_available} days</p>
                    </div>
                    <div className="p-3 border rounded">
                      <p className="text-slate-500 mb-1">Lead Days Needed</p>
                      <p className="font-medium">{c2_result.deadline?.deadline_gap?.lead_days_needed?.toFixed(1)} days</p>
                    </div>
                    <div className="p-3 border rounded">
                      <p className="text-slate-500 mb-1">Gap</p>
                      <p className={`font-bold ${c2_result.deadline?.deadline_gap?.gap_days > 0 ? 'text-red-600' : 'text-green-600'}`}>
                        {c2_result.deadline?.deadline_gap?.gap_days} days
                      </p>
                    </div>
                    <div className="p-3 border rounded">
                      <p className="text-slate-500 mb-1">Required Daily Comm.</p>
                      <p className="font-medium">{c2_result.deadline?.deadline_gap?.min_daily_commitment?.toLocaleString() || 'N/A'}</p>
                    </div>
                  </div>
                  {c2_result.deadline?.deadline_note && (
                    <div className="p-3 bg-red-50/50 rounded text-sm text-red-800 border border-red-100 flex space-x-2">
                      <AlertCircle className="w-5 h-5 flex-shrink-0 text-red-500" />
                      <span>{c2_result.deadline.deadline_note}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Allocation & Recommended Plants */}
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-100 bg-slate-50 flex items-center justify-between gap-2">
                  <h3 className="font-semibold text-slate-800">Plant Recommendations</h3>
                  {assignedPlants.length > 0 ? (
                    <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700 inline-flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Assigned
                    </span>
                  ) : !deadlineMatched ? (
                    <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-red-100 text-red-700">
                      Unavailable
                    </span>
                  ) : null}
                </div>

                {/* Assigned plants take priority - this is what actually happened. */}
                {assignedPlants.length > 0 && (
                  <div className="px-6 pt-6">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
                      Assigned to production
                    </h4>
                    <div className="space-y-2">
                      {assignedPlants.map((a: any, i: number) => (
                        <div key={i}
                             className="flex items-center justify-between gap-3 p-4 rounded-lg border-2 border-emerald-300 bg-emerald-50">
                          <div className="flex items-center gap-3 min-w-0">
                            <span className="w-8 h-8 rounded-full bg-emerald-600 text-white flex items-center justify-center shrink-0">
                              <Factory className="w-4 h-4" />
                            </span>
                            <div className="min-w-0">
                              <p className="font-semibold text-emerald-900 truncate">{a.plant_name}</p>
                              <p className="text-xs text-emerald-700">{a.allocation_type}</p>
                            </div>
                          </div>
                          <div className="text-right shrink-0">
                            <p className="font-bold text-emerald-900">{Number(a.allocated_qty || 0).toLocaleString()}</p>
                            <p className="text-xs text-emerald-700">pieces</p>
                          </div>
                        </div>
                      ))}
                    </div>
                    {assignedPlants.length > 1 && (
                      <p className="mt-2 text-xs text-slate-500">
                        Split across {assignedPlants.length} plants ·{" "}
                        {assignedPlants.reduce((t: number, a: any) => t + (a.allocated_qty || 0), 0).toLocaleString()} pcs total
                      </p>
                    )}
                  </div>
                )}

                {/* Deadline cannot be met and nothing assigned - explain, and show nothing else. */}
                {!deadlineMatched && assignedPlants.length === 0 ? (
                  <div className="p-6">
                    <div className="rounded-lg border border-red-200 bg-red-50 p-4 flex items-start gap-3">
                      <AlertCircle className="w-5 h-5 shrink-0 text-red-500 mt-0.5" />
                      <div>
                        <p className="text-sm font-semibold text-red-800">No plant can be recommended</p>
                        <p className="text-sm text-red-700 mt-1">
                          The deadline cannot be met with the current timeline and quantity. Adjust either,
                          or agree a new date with the buyer, then re-evaluate to get a recommendation.
                        </p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="p-6 space-y-6">
                    {/* Strategy */}
                    <div className="flex flex-wrap justify-between items-center gap-3 p-4 bg-indigo-50 rounded-lg border border-indigo-100">
                      <div>
                        <p className="text-xs text-indigo-600 font-semibold uppercase tracking-wide mb-1">Strategy</p>
                        <p className="text-lg font-bold text-indigo-900">{c2_result.allocation?.allocation_type}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-xs text-indigo-600 font-semibold uppercase tracking-wide mb-1">Split Probability</p>
                        <p className="text-lg font-bold text-indigo-900">
                          {((c2_result.allocation?.split_probability || 0) * 100).toFixed(1)}%
                        </p>
                      </div>
                    </div>

                    {c2_result.allocation?.allocation_note && (
                      <div className="p-3 bg-amber-50 rounded-lg text-sm text-amber-800 border border-amber-200 flex gap-2">
                        <Info className="w-5 h-5 flex-shrink-0 text-amber-600" />
                        <span>{c2_result.allocation.allocation_note}</span>
                      </div>
                    )}

                    {/* Ranking */}
                    <div>
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
                        {assignedPlants.length > 0 ? "AI ranking at assignment" : "AI ranking (all plants)"}
                      </h4>
                      <div className="space-y-2">
                        {c2_result.plant_recommendation?.ranking?.map((alloc: any, idx: number) => {
                          const isAssigned = assignedNames.has(alloc.plant);
                          return (
                            <div key={idx}
                                 className={`flex flex-wrap justify-between items-center gap-3 p-3 rounded-lg border transition-colors ${
                                   isAssigned
                                     ? "border-emerald-300 bg-emerald-50/70"
                                     : "border-slate-200 bg-white hover:bg-slate-50"}`}>
                              <div className="flex items-center gap-3 min-w-0">
                                <span className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold shrink-0 ${
                                  isAssigned ? "bg-emerald-600 text-white"
                                    : idx === 0 ? "bg-indigo-600 text-white" : "bg-slate-200 text-slate-700"}`}>
                                  {alloc.rank}
                                </span>
                                <span className={`font-medium truncate ${isAssigned ? "text-emerald-900" : "text-slate-800"}`}>
                                  {alloc.plant}
                                </span>
                                {isAssigned && (
                                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-600 text-white shrink-0">
                                    ASSIGNED
                                  </span>
                                )}
                              </div>
                              <div className="flex items-center gap-3 shrink-0">
                                {alloc.can_handle_solo ? (
                                  <span className="text-xs px-2 py-1 bg-green-100 text-green-700 rounded-full font-medium inline-flex items-center">
                                    <CheckCircle2 className="w-3 h-3 mr-1" /> Can handle solo
                                  </span>
                                ) : (
                                  <span className="text-xs px-2 py-1 bg-slate-100 text-slate-500 rounded-full font-medium">
                                    Needs split
                                  </span>
                                )}
                                <span className="text-sm text-slate-500 w-20 text-right tabular-nums">
                                  {alloc.score.toFixed(2)}
                                </span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                )}
              </div>

            </>
          ) : (
            <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
              {c2Error ? (
                <div className="flex flex-col items-center gap-2">
                  <AlertTriangle className="w-6 h-6 text-red-500" />
                  <p className="font-medium text-slate-700">AI feasibility analysis failed for this order.</p>
                  <p className="text-sm text-red-600">{c2Error}</p>
                  <p className="text-xs text-slate-400 mt-1">Plant recommendations and the timeline are unavailable. You can still assign a plant manually from the Bulk Orders list.</p>
                </div>
              ) : (
                <p className="text-slate-500">No AI Component 2 Allocation Data available.</p>
              )}
            </div>
          )}
        </div>
      </div>

      {assignOpen && (
        <AssignPlantModal
          order={order}
          plants={assignablePlants()}
          samplePlant={samplePlant()}
          isFallback={isFallbackPlants()}
          onClose={() => setAssignOpen(false)}
          onAssigned={() => { setAssignOpen(false); fetchOrder(); }}
        />
      )}
      {emailOpen && (
        <TimelineEmailModal
          order={order}
          onClose={() => setEmailOpen(false)}
          onSent={() => { setEmailOpen(false); fetchOrder(); }}
        />
      )}
    </div>
  );
}

function AssignPlantModal({ order, plants, samplePlant, isFallback, onClose, onAssigned }: {
  order: any; plants: any[]; samplePlant?: string; isFallback: boolean; onClose: () => void; onAssigned: () => void;
}) {
  const qty: number = order.bulk_order_quantity || 0;
  const strategy: string = order.c2_result?.allocation?.allocation_type || "";
  const wantsSplit = /split/i.test(strategy);

  const [rows, setRows] = useState<{ plant: string; qty: string }[]>(() => {
    const first = plants[0]?.plant || "";
    if (wantsSplit && plants.length >= 2) {
      const half = Math.floor(qty / 2);
      return [{ plant: first, qty: String(qty - half) }, { plant: plants[1].plant, qty: String(half) }];
    }
    return [{ plant: first, qty: String(qty) }];
  });
  const [saving, setSaving] = useState(false);

  const allocated = rows.reduce((s, r) => s + (parseInt(r.qty || "0", 10) || 0), 0);
  const remaining = qty - allocated;
  const usedPlants = rows.map((r) => r.plant).filter(Boolean);
  const dupPlants = new Set(usedPlants).size !== usedPlants.length;
  const optionsFor = (idx: number) => plants.filter((p) => p.plant === rows[idx].plant || !usedPlants.includes(p.plant));

  const setRow = (i: number, patch: Partial<{ plant: string; qty: string }>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const addRow = () => {
    const next = plants.find((p) => !usedPlants.includes(p.plant));
    setRows((rs) => [...rs, { plant: next?.plant || "", qty: String(Math.max(0, remaining)) }]);
  };
  const removeRow = (i: number) => setRows((rs) => rs.filter((_, j) => j !== i));

  const valid = rows.length > 0 && rows.every((r) => r.plant && (parseInt(r.qty, 10) || 0) > 0) && allocated === qty && !dupPlants;

  const submit = async () => {
    if (!valid) return;
    setSaving(true);
    try {
      await api.post(`/admin/orders/bulk/${order.id}/assign`, {
        allocations: rows.map((r, i) => ({
          plant_id: r.plant,
          allocation_type: i === 0 ? "Primary" : "Secondary",
          allocated_qty: parseInt(r.qty, 10),
        })),
      });
      Swal.fire({ icon: "success", title: rows.length > 1 ? "Split assigned — order is now Processing." : "Plant assigned — order is now Processing." });
      onAssigned();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to assign." });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-slate-800 mb-1 flex items-center gap-2">
          <Factory className="w-5 h-5 text-indigo-600" /> Assign Production
        </h3>
        <p className="text-sm text-slate-500 mb-4">
          Style {order.style_number} · {order.buyer_name} · <strong>{qty.toLocaleString()}</strong> pcs
        </p>

        {wantsSplit && (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 flex items-start gap-2">
            <Split className="w-4 h-4 shrink-0 mt-0.5" />
            <span>AI strategy is <strong>Split Between Sub Plants</strong> — no single plant can take the whole order. Divide it across plants below.</span>
          </div>
        )}
        {isFallback && (
          <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
            <span>AI plant ranking is unavailable — showing all plants.</span>
          </div>
        )}

        {plants.length === 0 ? (
          <p className="text-sm text-red-600">No plants available to assign.</p>
        ) : (
          <>
            <div className="space-y-2">
              {rows.map((r, i) => (
                <div key={i} className="flex items-center gap-2">
                  <select
                    className="flex-1 text-sm border border-slate-300 rounded-md py-2 px-2 bg-white"
                    value={r.plant}
                    onChange={(e) => setRow(i, { plant: e.target.value })}
                  >
                    <option value="">Select plant…</option>
                    {optionsFor(i).map((p: any) => (
                      <option key={p.plant} value={p.plant}>
                        {p.plant}{p.plant === samplePlant ? " (sample)" : ""}{p.can_handle_solo ? " · can solo" : ""}
                      </option>
                    ))}
                  </select>
                  <Input
                    type="number"
                    min={1}
                    className="w-28"
                    value={r.qty}
                    onChange={(e) => setRow(i, { qty: e.target.value })}
                    placeholder="Qty"
                  />
                  {rows.length > 1 && (
                    <button type="button" className="text-slate-400 hover:text-red-600 p-1" onClick={() => removeRow(i)} title="Remove">
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
              ))}
            </div>

            <div className="flex items-center justify-between mt-3">
              <Button variant="outline" size="sm" onClick={addRow} disabled={rows.length >= plants.length}>
                <Plus className="w-4 h-4 mr-1" /> Add plant
              </Button>
              <span className={`text-xs font-medium ${remaining === 0 ? "text-green-600" : "text-red-600"}`}>
                Allocated {allocated.toLocaleString()} / {qty.toLocaleString()}
                {remaining !== 0 && ` · ${remaining > 0 ? remaining.toLocaleString() + " left" : Math.abs(remaining).toLocaleString() + " over"}`}
              </span>
            </div>
            {dupPlants && <p className="mt-2 text-xs text-red-600">Each plant can only appear once.</p>}
          </>
        )}

        <div className="flex justify-end gap-2 mt-5">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={!valid || saving} className="bg-indigo-600 hover:bg-indigo-700">
            {saving ? "Assigning..." : rows.length > 1 ? "Assign Split" : "Assign"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function TimelineEmailModal({ order, onClose, onSent }: { order: any; onClose: () => void; onSent: () => void }) {
  const totalLead = order.c2_result?.production_days?.total_lead_days;
  const daysAvail = order.c2_result?.deadline?.deadline_gap?.days_available;
  const canByDefault = order.c2_result?.deadline?.deadline_match === "Match";

  const [decision, setDecision] = useState<"can_complete" | "cannot_complete">(canByDefault ? "can_complete" : "cannot_complete");
  const [given, setGiven] = useState(daysAvail ? String(daysAvail) : "");
  const [needed, setNeeded] = useState(totalLead ? String(Math.round(totalLead)) : "");
  const [sending, setSending] = useState(false);

  const gap = Math.abs((parseInt(given || "0", 10) || 0) - (parseInt(needed || "0", 10) || 0));

  const send = async () => {
    if (!given || !needed) {
      Swal.fire({ icon: "warning", title: "Enter both day counts." });
      return;
    }
    setSending(true);
    try {
      await api.post(`/admin/orders/bulk/${order.id}/timeline-email`, {
        decision, given_days: Number(given), needed_days: Number(needed), gap_days: gap,
      });
      Swal.fire({ icon: "success", title: "Timeline email sent", text: "Order moved to Customer Req. Pending." });
      onSent();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to send." });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-slate-800 mb-1">Completion Timeline Email</h3>
        <p className="text-sm text-slate-500 mb-4">Style {order.style_number} · {order.buyer_name}</p>

        <div className="flex gap-2 mb-4">
          <button onClick={() => setDecision("can_complete")}
            className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border ${decision === "can_complete" ? "bg-green-50 border-green-300 text-green-700" : "border-slate-200 text-slate-600"}`}>
            Can complete in time
          </button>
          <button onClick={() => setDecision("cannot_complete")}
            className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border ${decision === "cannot_complete" ? "bg-red-50 border-red-300 text-red-700" : "border-slate-200 text-slate-600"}`}>
            Needs an extension
          </button>
        </div>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Given days</label>
            <Input type="number" value={given} onChange={(e) => setGiven(e.target.value)} placeholder="e.g. 75" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Needed days</label>
            <Input type="number" value={needed} onChange={(e) => setNeeded(e.target.value)} placeholder="e.g. 68" />
          </div>
        </div>

        <div className="bg-slate-50 border border-slate-100 rounded-lg p-3 text-sm text-slate-600 mb-4">
          {decision === "can_complete"
            ? <>We can complete within the given schedule — <strong>{gap}</strong> day(s) to spare.</>
            : <>We need an extension of <strong>{gap}</strong> day(s) to take on the order.</>}
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={send} disabled={sending} className="bg-indigo-600 hover:bg-indigo-700">
            {sending ? "Sending..." : "Send Email"}
          </Button>
        </div>
      </div>
    </div>
  );
}
