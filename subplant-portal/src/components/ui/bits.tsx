"use client";

import React from "react";

/** Small shared building blocks used across the portal modules. */

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
      {children}
    </div>
  );
}

export function Card({ title, action, children }: {
  title: string; action?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
      <div className="flex items-center justify-between gap-3 mb-4">
        <h3 className="font-semibold text-slate-800">{title}</h3>
        {action}
      </div>
      {children}
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <p className="text-sm text-slate-500 py-12 text-center">{text}</p>;
}

const TONES: Record<string, string> = {
  teal: "bg-teal-50 text-teal-600",
  emerald: "bg-emerald-50 text-emerald-600",
  blue: "bg-blue-50 text-blue-600",
  indigo: "bg-indigo-50 text-indigo-600",
  amber: "bg-amber-50 text-amber-600",
  red: "bg-red-50 text-red-600",
  violet: "bg-violet-50 text-violet-600",
};

export function Stat({ icon, label, value, sub, tone = "teal" }: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  sub?: string;
  tone?: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center mb-3 ${TONES[tone] || TONES.teal}`}>
        {icon}
      </div>
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-slate-900 mt-1">{value ?? "—"}</p>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  );
}

export const STATUS_PILL: Record<string, string> = {
  Draft: "bg-slate-100 text-slate-600 border-slate-200",
  Confirmed: "bg-blue-100 text-blue-700 border-blue-200",
  "In Progress": "bg-amber-100 text-amber-700 border-amber-200",
  Completed: "bg-emerald-100 text-emerald-700 border-emerald-200",
  Cancelled: "bg-red-100 text-red-700 border-red-200",
  Pending: "bg-amber-100 text-amber-700 border-amber-200",
  Dispatched: "bg-blue-100 text-blue-700 border-blue-200",
  Received: "bg-emerald-100 text-emerald-700 border-emerald-200",
  Paid: "bg-emerald-100 text-emerald-700 border-emerald-200",
  Partial: "bg-blue-100 text-blue-700 border-blue-200",
  Overdue: "bg-red-100 text-red-700 border-red-200",
};

export function Pill({ value }: { value: string }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${
      STATUS_PILL[value] || "bg-slate-100 text-slate-600 border-slate-200"}`}>
      {value}
    </span>
  );
}

/** Dates from the API arrive as HTTP-date strings; normalise for display. */
export const fmtDate = (s?: string | null) => {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d.getTime()) ? String(s) : d.toLocaleDateString();
};

/** <input type="date"> needs YYYY-MM-DD. */
export const toDateInput = (s?: string | null) => {
  if (!s) return "";
  const d = new Date(s);
  return isNaN(d.getTime()) ? "" : d.toISOString().slice(0, 10);
};

export const money = (n: unknown) =>
  `Rs. ${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
