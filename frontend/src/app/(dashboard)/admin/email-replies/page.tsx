"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Mail, RefreshCw, ExternalLink } from "lucide-react";

const ACTION_PILL: Record<string, string> = {
  Approved: "bg-green-100 text-green-700",
  Rejected: "bg-orange-100 text-orange-700",
  Unclear: "bg-slate-100 text-slate-600",
};

export default function AdminEmailReplies() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);

  const fetchItems = async () => {
    try {
      const res = await api.get("/admin/inbound-email");
      setItems(res.data);
    } catch (err) {
      console.error("Failed to load email replies", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchItems(); }, []);

  const poll = async () => {
    setPolling(true);
    try {
      const res = await api.post("/admin/inbound-email/poll");
      const d = res.data;
      if (d.configured === false) Swal.fire({ icon: "info", title: "Not set up", text: d.message });
      else if (d.error) Swal.fire({ icon: "error", title: "Inbox error", text: d.error });
      else Swal.fire({ icon: "success", title: "Inbox checked", text: `${d.fetched} new, ${d.applied} applied.` });
      fetchItems();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to check inbox." });
    } finally {
      setPolling(false);
    }
  };

  if (loading) return <div>Loading...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center">
            <Mail className="w-6 h-6 mr-2 text-indigo-600" /> Customer Email Replies
          </h2>
          <p className="text-sm text-slate-500 mt-1">Replies to timeline emails, read from the mailbox and matched to orders.</p>
        </div>
        <Button variant="outline" onClick={poll} disabled={polling}>
          <RefreshCw className={`w-4 h-4 mr-1 ${polling ? "animate-spin" : ""}`} /> {polling ? "Checking..." : "Check Now"}
        </Button>
      </div>

      {items.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
          <p className="text-slate-500">No email replies captured yet.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((m) => (
            <div key={m.id} className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-slate-900">{m.from_addr}</span>
                    {m.detected_action && (
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${ACTION_PILL[m.detected_action] || "bg-slate-100 text-slate-600"}`}>
                        {m.detected_action}{m.extension_days ? ` · +${m.extension_days}d` : ""}
                      </span>
                    )}
                    {m.applied ? (
                      <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">Auto-applied</span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">Needs review</span>
                    )}
                  </div>
                  <p className="text-sm text-slate-500 mt-1 truncate">{m.subject}</p>
                </div>
                {m.order_id && (
                  m.order_type === "sample" ? (
                    <Button variant="ghost" size="sm" onClick={() => router.push(`/admin/samples`)}>
                      Sample #{m.order_id} {m.style_number ? `(${m.style_number})` : ""} <ExternalLink className="w-3.5 h-3.5 ml-1" />
                    </Button>
                  ) : (
                    <Button variant="ghost" size="sm" onClick={() => router.push(`/admin/bulk/${m.order_id}`)}>
                      Order #{m.order_id} {m.style_number ? `(${m.style_number})` : ""} <ExternalLink className="w-3.5 h-3.5 ml-1" />
                    </Button>
                  )
                )}
              </div>
              {m.body && (
                <p className="mt-3 text-sm text-slate-700 bg-slate-50 border border-slate-100 rounded-lg p-3 whitespace-pre-line">{m.body}</p>
              )}
              {m.note && <p className="mt-2 text-xs text-slate-400">{m.note}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
