"use client";
import { useState, useEffect } from "react";
import { Input } from "@/components/ui/Input";

/**
 * Shared type-ahead style picker used by both the sample and bulk order forms,
 * so the style list behaves identically in both. Shows all matching approved
 * styles (scrollable) rather than an arbitrary few.
 */
export default function StyleAutocomplete({
  styles,
  onSelect,
  placeholder = "Type to search e.g. ART-001",
  resetKey = 0,
  presetValue = "",
}: {
  styles: any[];
  onSelect: (style: any | null) => void; // full style object, or null when cleared
  placeholder?: string;
  resetKey?: number;
  presetValue?: string; // seeds the input (e.g. arriving from a completed sample)
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  // Clear the field when the parent resets (e.g. after submit).
  useEffect(() => { setQuery(""); }, [resetKey]);

  // Seed the input when the parent supplies a preset (deep link from a completed
  // sample order). Keyed on presetValue only, so it never fights with typing.
  useEffect(() => {
    if (presetValue) setQuery(presetValue);
  }, [presetValue]);

  const q = query.trim().toLowerCase();
  const matches = styles.filter((s) => {
    if (!q) return true;
    return (
      s.style_number?.toLowerCase().includes(q) ||
      s.style_name?.toLowerCase().includes(q)
    );
  });

  const pick = (style: any) => {
    setQuery(style.style_number);
    setOpen(false);
    onSelect(style);
  };

  const onType = (value: string) => {
    setQuery(value);
    setOpen(true);
    onSelect(null); // typing clears any prior selection until re-picked
  };

  return (
    <div className="relative">
      <Input
        value={query}
        onChange={(e) => onType(e.target.value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder}
        autoComplete="off"
      />
      {open && matches.length > 0 && (
        <ul className="absolute z-20 mt-1 w-full bg-white border border-slate-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
          {matches.map((s) => (
            <li key={s.style_number}>
              <button
                type="button"
                onMouseDown={(e) => { e.preventDefault(); pick(s); }}
                className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50"
              >
                <span className="font-medium text-slate-900">{s.style_number}</span>
                {s.style_name && <span className="text-slate-500"> — {s.style_name}</span>}
                {s.garment_type && <span className="text-slate-400"> · {s.garment_type}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && query.trim() && matches.length === 0 && (
        <div className="absolute z-20 mt-1 w-full bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2 text-sm text-slate-500">
          No matching styles in the catalog.
        </div>
      )}
    </div>
  );
}
