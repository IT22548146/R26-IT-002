"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import api from "@/lib/api";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Shirt, Plus, FileText, Info } from "lucide-react";

const STATUS_PILL: Record<string, string> = {
  Pending: "bg-amber-100 text-amber-700",
  Approved: "bg-green-100 text-green-700",
  Rejected: "bg-red-100 text-red-700",
};

export default function BuyerStyles() {
  const [styles, setStyles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchStyles = async () => {
    try {
      const res = await api.get("/buyer/styles");
      setStyles(res.data);
    } catch (err) {
      console.error("Failed to load styles", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchStyles(); }, []);

  const viewPdf = async (styleNumber: string) => {
    try {
      const res = await api.get(`/buyer/styles/${styleNumber}/pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      window.open(url, "_blank", "noopener,noreferrer");
      setTimeout(() => window.URL.revokeObjectURL(url), 60_000);
    } catch {
      Swal.fire({ icon: "error", title: "Error", text: "Failed to open the PDF." });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <Shirt className="w-6 h-6 mr-2 text-blue-600" /> My Styles
        </h2>
        <Link href="/buyer/samples?new=1">
          <Button className="bg-blue-600 hover:bg-blue-700">
            <Plus className="w-4 h-4 mr-1" /> New Sample Request
          </Button>
        </Link>
      </div>

      <p className="text-sm text-slate-500 -mt-2">
        Have a style that isn't in the catalog yet? Submit it here with a PDF. Once the team
        approves it, it becomes selectable when you place sample or bulk orders.
      </p>


      <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900 flex items-start gap-2 mb-6">
        <Info className="w-4 h-4 mt-0.5 shrink-0" />
        <span>
          Styles are registered when you raise a sample request — every sample is for a new style.
          Start a <Link href="/buyer/samples?new=1" className="underline font-medium">New Sample Request</Link> to add one.
        </span>
      </div>

      {loading ? (
        <div>Loading...</div>
      ) : styles.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
          <p className="text-slate-500">You haven't submitted any styles yet.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {styles.map((s) => (
            <div key={s.style_number} className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-3">
                  <span className="font-bold text-slate-900">{s.style_number}</span>
                  <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${STATUS_PILL[s.status] || "bg-slate-100 text-slate-600"}`}>{s.status}</span>
                </div>
                <p className="text-sm text-slate-500 mt-1">
                  {s.style_name || "—"}{s.garment_type ? ` · ${s.garment_type}` : ""} · Colours {s.color_count} · Stitches {s.stitch_count}
                </p>
                {s.status === "Rejected" && s.reject_reason && (
                  <p className="text-xs text-red-600 mt-1">Reason: {s.reject_reason}</p>
                )}
              </div>
              {s.style_pdf_path && (
                <Button variant="outline" onClick={() => viewPdf(s.style_number)}>
                  <FileText className="w-4 h-4 mr-1" /> View PDF
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

