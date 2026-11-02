import { Check, Clock, Scissors, Sparkles, Shirt, Package, Truck, PackageCheck, Ban, PauseCircle } from "lucide-react";

// Garment production stages — the single source of truth for the tracker.
export const PRODUCTION_STAGES = [
  { key: "Pending", label: "Pending", icon: Clock },
  { key: "Cutting", label: "Cutting", icon: Scissors },
  { key: "Embroidery", label: "Embroidery", icon: Sparkles },
  { key: "Sewing", label: "Sewing", icon: Shirt },
  { key: "Packing", label: "Packing", icon: Package },
  { key: "Shipping", label: "Shipping", icon: Truck },
  { key: "Delivery", label: "Delivery", icon: PackageCheck },
] as const;

export const STAGE_KEYS = PRODUCTION_STAGES.map((s) => s.key);

/** Dropdown for plant/admin to advance an order's production stage. */
export function StageSelect({ value, onChange, disabled }: {
  value: string; onChange: (stage: string) => void; disabled?: boolean;
}) {
  return (
    <label className="inline-flex items-center gap-2 text-sm">
      <span className="text-slate-500">Production stage:</span>
      <select
        value={value || "Pending"}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-950 disabled:opacity-50"
      >
        {STAGE_KEYS.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
    </label>
  );
}

/**
 * Progress + any status-level callout (Cancelled / On hold / Awaiting approval)
 * shown above the production bar.
 */
export function deriveTracker(type: "sample" | "bulk", order: any): {
  reached: number; complete: boolean;
  special?: { kind: "cancelled" | "hold" | "await"; text: string };
} {
  const stage = order.production_stage || "Pending";
  const reached = Math.max(0, STAGE_KEYS.indexOf(stage));
  const complete = stage === "Delivery";

  let special;
  if (order.status === "Cancelled") special = { kind: "cancelled" as const, text: "This order was cancelled." };
  else if (order.status === "Hold") special = { kind: "hold" as const, text: "This order is currently on hold." };
  else if (order.status === "CustomerPending") special = { kind: "await" as const, text: "Awaiting your approval of the proposed timeline." };

  return { reached, complete, special };
}

const SPECIAL_STYLE = {
  cancelled: { bg: "bg-red-50 border-red-200 text-red-700", icon: Ban },
  hold: { bg: "bg-orange-50 border-orange-200 text-orange-700", icon: PauseCircle },
  await: { bg: "bg-purple-50 border-purple-200 text-purple-700", icon: Clock },
};

export default function OrderTracker({ type, order, tone = "blue" }: {
  type: "sample" | "bulk"; order: any; tone?: "blue" | "indigo";
}) {
  const { reached, complete, special } = deriveTracker(type, order);
  const accent = tone === "indigo" ? "bg-indigo-600" : "bg-blue-600";
  const accentText = tone === "indigo" ? "text-indigo-600" : "text-blue-600";
  const ring = tone === "indigo" ? "ring-indigo-100" : "ring-blue-100";
  const cancelled = special?.kind === "cancelled";

  return (
    <div>
      {special && (() => {
        const s = SPECIAL_STYLE[special.kind];
        const SIcon = s.icon;
        return (
          <div className={`mb-4 flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${s.bg}`}>
            <SIcon className="w-4 h-4 shrink-0" /> {special.text}
          </div>
        );
      })()}

      <div className="overflow-x-auto">
        <div className="flex items-start min-w-[520px]">
          {PRODUCTION_STAGES.map((step, i) => {
            const isDone = !cancelled && (complete || i < reached);
            const isCurrent = !cancelled && !complete && i === reached;
            const Icon = isDone ? Check : step.icon;
            const circle = isDone
              ? "bg-green-500 text-white border-green-500"
              : isCurrent
              ? `${accent} text-white border-transparent ring-4 ${ring}`
              : "bg-white text-slate-400 border-slate-300";
            const line = !cancelled && (complete || i < reached) ? "bg-green-500" : "bg-slate-200";
            return (
              <div key={step.key} className="flex-1 flex flex-col items-center relative">
                {i > 0 && <span className={`absolute top-4 right-1/2 left-[-50%] h-1 ${line}`} />}
                <div className={`relative z-10 w-8 h-8 rounded-full border-2 flex items-center justify-center ${circle}`}>
                  <Icon className="w-4 h-4" />
                </div>
                <p className={`mt-2 text-xs font-medium text-center leading-tight ${
                  isCurrent ? accentText : isDone ? "text-slate-700" : "text-slate-400"
                }`}>
                  {step.label}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
