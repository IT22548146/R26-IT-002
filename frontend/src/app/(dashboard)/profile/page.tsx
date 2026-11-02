"use client";

import { useState, useEffect } from "react";
import Swal from "@/lib/swal";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { PhoneField, isValidPhoneNumber } from "@/components/ui/PhoneField";
import type { Country } from "react-phone-number-input";
import { UserCircle, Mail, Building2, ShieldCheck } from "lucide-react";

// Turn an ISO country code (e.g. "LK") into a display name (e.g. "Sri Lanka").
const REGION_NAMES =
  typeof Intl !== "undefined" && "DisplayNames" in Intl
    ? new Intl.DisplayNames(["en"], { type: "region" })
    : null;

export default function ProfilePage() {
  const { user, refreshUser } = useAuth();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [newPic, setNewPic] = useState<File | null>(null);
  const [form, setForm] = useState({
    full_name: "",
    contact_no: "",
    country: "",
    address: "",
  });

  // Seed the form from the current user.
  useEffect(() => {
    if (user) {
      setForm({
        full_name: user.full_name || "",
        contact_no: user.contact_no || "",
        country: user.country || "",
        address: user.address || "",
      });
    }
  }, [user]);

  // Load the profile photo (authenticated blob) if one exists.
  useEffect(() => {
    let revoked: string | null = null;
    if (user?.profile_pic_path) {
      api.get("/auth/profile/photo", { responseType: "blob" })
        .then((res) => {
          const url = URL.createObjectURL(res.data);
          revoked = url;
          setPhotoUrl(url);
        })
        .catch(() => setPhotoUrl(null));
    }
    return () => { if (revoked) URL.revokeObjectURL(revoked); };
  }, [user?.profile_pic_path]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.full_name.trim()) {
      Swal.fire({ icon: "warning", title: "Full name cannot be empty." });
      return;
    }
    if (form.contact_no && !isValidPhoneNumber(form.contact_no)) {
      Swal.fire({
        icon: "warning",
        title: "Invalid phone number",
        text: "Please enter a valid phone number, including the country code.",
      });
      return;
    }
    setSaving(true);
    try {
      const payload = new FormData();
      Object.entries(form).forEach(([k, v]) => payload.append(k, v));
      if (newPic) payload.append("profile_pic", newPic);
      await api.put("/auth/profile", payload);
      await refreshUser();
      setEditing(false);
      setNewPic(null);
      Swal.fire({ icon: "success", title: "Profile updated" });
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Update failed." });
    } finally {
      setSaving(false);
    }
  };

  if (!user) return <div>Loading...</div>;

  const roleLabel = user.role === "PlantManager" ? "Plant Manager" : user.role;

  return (
    <div className="max-w-3xl space-y-6">
      <h2 className="text-xl font-bold text-slate-800 flex items-center">
        <UserCircle className="w-6 h-6 mr-2 text-blue-600" /> My Profile
      </h2>

      {/* Identity card */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex items-center gap-5">
        <div className="w-20 h-20 rounded-full bg-slate-100 overflow-hidden flex items-center justify-center shrink-0">
          {photoUrl ? (
            <img src={photoUrl} alt="Profile" className="w-full h-full object-cover" />
          ) : (
            <UserCircle className="w-12 h-12 text-slate-300" />
          )}
        </div>
        <div className="min-w-0">
          <p className="text-lg font-bold text-slate-900 truncate">{user.full_name}</p>
          <p className="text-sm text-slate-500 flex items-center gap-1"><Mail className="w-3.5 h-3.5" /> {user.email}</p>
          <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
            <span className="flex items-center gap-1"><ShieldCheck className="w-3.5 h-3.5" /> {roleLabel}</span>
            {user.org_name && <span className="flex items-center gap-1"><Building2 className="w-3.5 h-3.5" /> {user.org_name}</span>}
          </div>
        </div>
        {!editing && (
          <Button variant="outline" className="ml-auto" onClick={() => setEditing(true)}>Edit Profile</Button>
        )}
      </div>

      {/* Details / edit form */}
      <form onSubmit={handleSave} className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-4">
        <h3 className="text-sm font-semibold text-slate-700">Details</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Full Name" value={form.full_name} editing={editing}
            onChange={(v) => setForm({ ...form, full_name: v })} />
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Contact No</label>
            {editing ? (
              <>
                <PhoneField
                  value={form.contact_no}
                  onChange={(v) => setForm({ ...form, contact_no: v })}
                  onCountryChange={(c: Country | undefined) => {
                    const name = c ? REGION_NAMES?.of(c) : undefined;
                    if (name) setForm((f) => ({ ...f, country: name }));
                  }}
                  defaultCountry="LK"
                  error={form.contact_no.length > 0 && !isValidPhoneNumber(form.contact_no)}
                />
                {form.contact_no.length > 0 && !isValidPhoneNumber(form.contact_no) && (
                  <p className="mt-1 text-xs text-red-600">Enter a valid phone number for the selected country.</p>
                )}
              </>
            ) : (
              <p className="text-sm text-slate-900">{form.contact_no || "—"}</p>
            )}
          </div>
          <Field label="Country" value={form.country} editing={editing}
            onChange={(v) => setForm({ ...form, country: v })} placeholder="—" />
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-slate-700 mb-1">Address</label>
            {editing ? (
              <textarea rows={2} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-950" />
            ) : (
              <p className="text-sm text-slate-900">{form.address || "—"}</p>
            )}
          </div>
          {editing && (
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-slate-700 mb-1">Change Profile Picture <span className="text-slate-400 font-normal">(optional)</span></label>
              <Input type="file" accept="image/png,image/jpeg,image/webp"
                onChange={(e) => setNewPic(e.target.files?.[0] ?? null)}
                className="file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1 file:text-sm file:text-slate-700 hover:file:bg-slate-200 cursor-pointer py-1.5" />
              {newPic && <p className="mt-1 text-xs text-slate-500 truncate">Selected: {newPic.name}</p>}
            </div>
          )}
        </div>

        {editing && (
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => { setEditing(false); setNewPic(null); }}>Cancel</Button>
            <Button type="submit" disabled={saving}>{saving ? "Saving..." : "Save Changes"}</Button>
          </div>
        )}
      </form>
    </div>
  );
}

function Field({ label, value, editing, onChange, placeholder }: {
  label: string; value: string; editing: boolean; onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
      {editing ? (
        <Input value={value} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <p className="text-sm text-slate-900">{value || placeholder || "—"}</p>
      )}
    </div>
  );
}
