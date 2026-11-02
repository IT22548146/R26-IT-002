"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { PhoneField, isValidPhoneNumber } from "@/components/ui/PhoneField";
import type { Country } from "react-phone-number-input";
import Link from "next/link";
import { Building2 } from "lucide-react";

// Turn an ISO country code (e.g. "LK") into a display name (e.g. "Sri Lanka").
const REGION_NAMES =
  typeof Intl !== "undefined" && "DisplayNames" in Intl
    ? new Intl.DisplayNames(["en"], { type: "region" })
    : null;

export default function RegisterPage() {
  const [formData, setFormData] = useState({
    company_name: "",
    full_name: "",
    email: "",
    password: "",
    contact_no: "",
    country: "",
    address: "",
  });
  const [profilePic, setProfilePic] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (profilePic && !/\.(png|jpe?g|webp)$/i.test(profilePic.name)) {
      setError("Profile picture must be a PNG, JPG, or WEBP image.");
      return;
    }

    if (!isValidPhoneNumber(formData.contact_no)) {
      setError("Please enter a valid phone number, including the country code.");
      return;
    }

    setLoading(true);
    try {
      const payload = new FormData();
      Object.entries(formData).forEach(([k, v]) => payload.append(k, v));
      if (profilePic) payload.append("profile_pic", profilePic);
      await api.post("/auth/register", payload);
      setSuccess(true);
    } catch (err: any) {
      setError(err.response?.data?.error || "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900 bg-[url('/bg_image.png')] bg-cover bg-center bg-no-repeat bg-fixed py-12 px-4 sm:px-6 lg:px-8 relative overflow-hidden">
        
        {/* Wave Background */}
        <div className="absolute bottom-0 left-0 right-0 pointer-events-none" style={{ zIndex: 0 }}>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 320" className="w-full h-auto drop-shadow-xl">
            <path fill="#0f172a" fillOpacity="1" d="M0,160L48,170.7C96,181,192,203,288,197.3C384,192,480,160,576,160C672,160,768,192,864,208C960,224,1056,224,1152,192C1248,160,1344,96,1392,64L1440,32L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z"></path>
          </svg>
        </div>

        <div className="max-w-md w-full space-y-8 bg-white p-10 rounded-xl shadow-2xl border border-slate-100 text-center relative z-10">
          <div className="mx-auto h-12 w-12 bg-green-100 rounded-full flex items-center justify-center mb-4 shadow-sm">
            <svg className="h-6 w-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Registration Successful</h2>
          <p className="text-slate-600 mt-2">
            Your buyer account has been created and is pending Admin approval. You will receive an email once your account is activated.
          </p>
          <div className="mt-6">
            <Link href="/login">
              <Button className="w-full shadow-md hover:shadow-lg transition-shadow">Return to Login</Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900 bg-[url('/bg_image.png')] bg-cover bg-center bg-no-repeat bg-fixed py-12 px-4 sm:px-6 lg:px-8 relative overflow-hidden">
      
      {/* Wave Background */}
      <div className="absolute bottom-0 left-0 right-0 pointer-events-none transform scale-y-[1.5] origin-bottom" style={{ zIndex: 0 }}>
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 320" className="w-full h-auto drop-shadow-xl">
          <path fill="#0f172a" fillOpacity="1" d="M0,160L48,170.7C96,181,192,203,288,197.3C384,192,480,160,576,160C672,160,768,192,864,208C960,224,1056,224,1152,192C1248,160,1344,96,1392,64L1440,32L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z"></path>
        </svg>
      </div>

      <div className="max-w-md w-full space-y-8 bg-white p-10 rounded-xl shadow-2xl border border-slate-100 relative z-10">
        <div className="flex flex-col items-center">
          <div className="h-12 w-12 bg-blue-600 rounded-lg flex items-center justify-center">
            <Building2 className="h-6 w-6 text-white" />
          </div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-slate-900">
            Registration
          </h2>
          <p className="mt-2 text-center text-sm text-slate-600">
            Apply for a FabricFlow wholesale account
          </p>
        </div>
        
        <form className="mt-8 space-y-6" onSubmit={handleRegister}>
          {error && (
            <div className="bg-red-50 text-red-600 p-3 rounded-lg text-sm border border-red-100">
              {error}
            </div>
          )}
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Company Name
              </label>
              <Input
                required
                value={formData.company_name}
                onChange={(e) => setFormData({ ...formData, company_name: e.target.value })}
                placeholder="e.g. Tesco"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Your Full Name
              </label>
              <Input
                required
                value={formData.full_name}
                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                placeholder="John Doe"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Email address
              </label>
              <Input
                type="email"
                required
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="john@tesco.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Password
              </label>
              <Input
                type="password"
                required
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                placeholder="••••••••"
                minLength={8}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Contact No *</label>
              <PhoneField
                value={formData.contact_no}
                onChange={(v) => setFormData({ ...formData, contact_no: v })}
                onCountryChange={(c: Country | undefined) => {
                  const name = c ? REGION_NAMES?.of(c) : undefined;
                  if (name) setFormData((f) => ({ ...f, country: name }));
                }}
                defaultCountry="LK"
                error={formData.contact_no.length > 0 && !isValidPhoneNumber(formData.contact_no)}
              />
              {formData.contact_no.length > 0 && !isValidPhoneNumber(formData.contact_no) && (
                <p className="mt-1 text-xs text-red-600">Enter a valid phone number for the selected country.</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Country *</label>
              <Input required value={formData.country} onChange={(e) => setFormData({ ...formData, country: e.target.value })} placeholder="Sri Lanka" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Address *</label>
              <textarea
                required
                rows={2}
                value={formData.address}
                onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                placeholder="Street, City"
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-950"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Profile Picture <span className="text-slate-400 font-normal">(optional)</span>
              </label>
              <Input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={(e) => setProfilePic(e.target.files?.[0] ?? null)}
                className="file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1 file:text-sm file:text-slate-700 hover:file:bg-slate-200 cursor-pointer py-1.5"
              />
              {profilePic && <p className="mt-1 text-xs text-slate-500 truncate">Selected: {profilePic.name}</p>}
            </div>
          </div>

          <Button type="submit" className="w-full bg-blue-600 hover:bg-blue-700" disabled={loading}>
            {loading ? "Registering..." : "Register"}
          </Button>

          <div className="text-center text-sm">
            <span className="text-slate-600">Already have an account? </span>
            <Link href="/login" className="font-medium text-slate-900 hover:text-slate-700 transition-colors">
              Sign in
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
