"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Shirt, Download, Check, X } from "lucide-react";

/** Pending style-submission review — shared by admin and plant managers. */
export default function StyleReview({ accent = "blue" }: { accent?: "blue" | "emerald" }) {
  const [subs, setSubs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [reasons, setReasons] = useState<Record<string, string>>({});

  const fetchSubs = async () => {
    try {
      const res = await api.get("/styles/submissions");
      setSubs(res.data);
    } catch (err) {
      console.error("Failed to load submissions", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchSubs(); }, []);

  const downloadPdf = async (styleNumber: string) => {
    try {
      const res = await api.get(`/styles/${styleNumber}/pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `${styleNumber}_style.pdf`; a.click();
      setTimeout(() => window.URL.revokeObjectURL(url), 10_000);
    } catch {
      Swal.fire({ icon: "error", title: "Error", text: "Failed to download the PDF." });
    }
  };

  const approve = async (styleNumber: string) => {
    setBusy(styleNumber);
    try {
      await api.post(`/styles/${styleNumber}/approve`);
      Swal.fire({ icon: "success", title: `Approved ${styleNumber}`, text: "The buyer has been emailed." });
      fetchSubs();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to approve." });
    } finally {
      setBusy(null);
    }
  };

  const reject = async (styleNumber: string, reason: string) => {
    const ok = await Swal.fire({
      title: `Reject ${styleNumber}?`, text: reason ? `Reason: ${reason}` : "The buyer will be notified.",
      icon: "warning", showCancelButton: true, confirmButtonText: "Reject", confirmButtonColor: "#dc2626",
    });
    if (!ok.isConfirmed) return;
    setBusy(styleNumber);
    try {
      await api.post(`/styles/${styleNumber}/reject`, { reason: reason || "" });
      Swal.fire({ icon: "success", title: `Rejected ${styleNumber}`, text: "The buyer has been notified." });
      fetchSubs();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to reject." });
    } finally {
      setBusy(null);
    }
  };

  const accentText = accent === "emerald" ? "text-emerald-600" : "text-blue-600";

  if (loading) return <div>Loading...</div>;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <Shirt className={`w-6 h-6 mr-2 ${accentText}`} /> Style Submissions
        </h2>
        <p className="text-sm text-slate-500 mt-1">Review styles submitted by buyers. Approving one adds it to the catalog.</p>
      </div>

      {subs.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
          <p className="text-slate-500">No style submissions awaiting review.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {subs.map((s) => (
            <div key={s.style_number} className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-3 mb-1">
                    <span className="text-lg font-bold text-slate-900">{s.style_number}</span>
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">Pending</span>
                  </div>
                  <p className="text-sm text-slate-500">
                    {s.style_name || "—"}{s.garment_type ? ` · ${s.garment_type}` : ""}
                    {" · by "}<strong className="text-slate-700">{s.submitted_by_name}</strong>
                    {s.company_name ? ` (${s.company_name})` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {s.style_pdf_path && (
                    <Button variant="outline" onClick={() => downloadPdf(s.style_number)}>
                      <Download className="w-4 h-4 mr-1" /> PDF
                    </Button>
                  )}
                  <Button className="bg-green-600 hover:bg-green-700" disabled={busy === s.style_number} onClick={() => approve(s.style_number)}>
                    <Check className="w-4 h-4 mr-1" /> Approve
                  </Button>
                  <Button variant="danger" disabled={busy === s.style_number} onClick={() => reject(s.style_number, reasons[s.style_number] || "")}>
                    <X className="w-4 h-4 mr-1" /> Reject
                  </Button>
                </div>
              </div>

              <input
                value={reasons[s.style_number] || ""}
                onChange={(e) => setReasons({ ...reasons, [s.style_number]: e.target.value })}
                placeholder="Optional rejection reason…"
                className="mt-3 w-full h-9 rounded-lg border border-slate-200 px-3 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-950"
              />

              <div className="mt-4 grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                <Spec label="Design Width" value={`${s.design_width} cm`} />
                <Spec label="Design Length" value={`${s.design_length} cm`} />
                <Spec label="Colours" value={s.color_count} />
                <Spec label="Stitch Count" value={s.stitch_count} />
                <Spec label="Complexity" value={s.complexity || "—"} />
              </div>
              {s.description && <p className="mt-3 text-sm text-slate-600 italic">"{s.description}"</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Spec({ label, value }: { label: string; value: any }) {
  return (
    <div className="bg-slate-50 border border-slate-100 rounded-lg px-3 py-2">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="text-sm font-semibold text-slate-800">{value ?? "—"}</p>
    </div>
  );
}
