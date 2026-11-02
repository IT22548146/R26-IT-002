"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, XCircle, AlertTriangle, Info, X } from "lucide-react";

type Variant = "success" | "error" | "warning" | "info";

export type ToastRecord = {
  id: number;
  variant: Variant;
  title?: string;
  message: string;
  duration: number; // ms; 0 = sticky (used for confirms)
  confirm?: {
    confirmText: string;
    cancelText: string;
    danger?: boolean;
    resolve: (v: boolean) => void;
  };
};

let counter = 0;
let current: ToastRecord[] = [];
let listeners: Array<(list: ToastRecord[]) => void> = [];

function emit() {
  listeners.forEach((l) => l(current));
}

function add(t: Omit<ToastRecord, "id">): number {
  const id = ++counter;
  current = [...current, { ...t, id }];
  emit();
  if (t.duration > 0) {
    setTimeout(() => remove(id), t.duration);
  }
  return id;
}

function remove(id: number) {
  const item = current.find((t) => t.id === id);
  // A dismissed confirm resolves to false (treated as cancel).
  if (item?.confirm) item.confirm.resolve(false);
  current = current.filter((t) => t.id !== id);
  emit();
}

/** Global toast API — import and call from anywhere. */
export const toast = {
  success: (message: string, title?: string) => add({ variant: "success", message, title, duration: 4000 }),
  error: (message: string, title?: string) => add({ variant: "error", message, title, duration: 6000 }),
  warning: (message: string, title?: string) => add({ variant: "warning", message, title, duration: 5000 }),
  info: (message: string, title?: string) => add({ variant: "info", message, title, duration: 4000 }),
  confirm: (opts: { title?: string; message?: string; confirmText?: string; cancelText?: string; danger?: boolean }) =>
    new Promise<boolean>((resolve) => {
      let settled = false;
      const done = (v: boolean) => { if (!settled) { settled = true; resolve(v); } };
      const id = add({
        variant: opts.danger ? "warning" : "info",
        title: opts.title,
        message: opts.message || "",
        duration: 0,
        confirm: {
          confirmText: opts.confirmText || "Confirm",
          cancelText: opts.cancelText || "Cancel",
          danger: opts.danger,
          resolve: (v: boolean) => done(v),
        },
      });
      // store id via closure so buttons can dismiss it
      (opts as any).__id = id;
    }),
};

const STYLES: Record<Variant, { icon: any; ring: string; iconColor: string; bar: string }> = {
  success: { icon: CheckCircle2, ring: "border-green-200", iconColor: "text-green-600", bar: "bg-green-500" },
  error: { icon: XCircle, ring: "border-red-200", iconColor: "text-red-600", bar: "bg-red-500" },
  warning: { icon: AlertTriangle, ring: "border-amber-200", iconColor: "text-amber-600", bar: "bg-amber-500" },
  info: { icon: Info, ring: "border-blue-200", iconColor: "text-blue-600", bar: "bg-blue-500" },
};

/** Mount once (in the root layout). Renders toasts bottom-right. */
export function Toaster() {
  const [items, setItems] = useState<ToastRecord[]>([]);

  useEffect(() => {
    const l = (list: ToastRecord[]) => setItems([...list]);
    listeners.push(l);
    setItems([...current]);
    return () => { listeners = listeners.filter((x) => x !== l); };
  }, []);

  const answer = (item: ToastRecord, value: boolean) => {
    if (item.confirm) item.confirm.resolve(value);
    // remove without re-resolving
    current = current.filter((t) => t.id !== item.id);
    emit();
  };

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-3 w-[calc(100vw-2rem)] max-w-sm pointer-events-none">
      {items.map((item) => {
        const s = STYLES[item.variant];
        const Icon = s.icon;
        return (
          <div
            key={item.id}
            role="alert"
            className={`pointer-events-auto relative overflow-hidden bg-white rounded-xl shadow-lg border ${s.ring} animate-in slide-in-from-bottom-4 fade-in duration-300`}
          >
            <span className={`absolute left-0 top-0 bottom-0 w-1 ${s.bar}`} />
            <div className="flex items-start gap-3 p-4 pl-5">
              <Icon className={`w-5 h-5 mt-0.5 shrink-0 ${s.iconColor}`} />
              <div className="flex-1 min-w-0">
                {item.title && <p className="text-sm font-semibold text-slate-900">{item.title}</p>}
                {item.message && (
                  <p className={`text-sm text-slate-600 ${item.title ? "mt-0.5" : "font-medium text-slate-800"} whitespace-pre-line break-words`}>
                    {item.message}
                  </p>
                )}
                {item.confirm && (
                  <div className="flex gap-2 mt-3">
                    <button
                      onClick={() => answer(item, true)}
                      className={`px-3 py-1.5 text-sm font-semibold rounded-lg text-white transition-colors ${
                        item.confirm.danger ? "bg-red-600 hover:bg-red-700" : "bg-blue-600 hover:bg-blue-700"
                      }`}
                    >
                      {item.confirm.confirmText}
                    </button>
                    <button
                      onClick={() => answer(item, false)}
                      className="px-3 py-1.5 text-sm font-medium rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors"
                    >
                      {item.confirm.cancelText}
                    </button>
                  </div>
                )}
              </div>
              {!item.confirm && (
                <button onClick={() => remove(item.id)} className="text-slate-400 hover:text-slate-600 shrink-0" aria-label="Dismiss">
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
