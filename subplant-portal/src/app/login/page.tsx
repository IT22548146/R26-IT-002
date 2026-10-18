"use client";

import { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Factory } from "lucide-react";
import { getApiErrorMessage } from "@/lib/errors";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.post("/auth/login", { email, password });
      await login(res.data.token);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Sign in failed."));
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900 px-4 py-12 relative overflow-hidden">
      {/* Wave backdrop, mirroring the main FabricFlow sign-in */}
      <div className="absolute bottom-0 left-0 right-0 pointer-events-none" style={{ zIndex: 0 }}>
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 320" className="w-full h-auto">
          <path fill="#0f172a" fillOpacity="1" d="M0,160L48,170.7C96,181,192,203,288,197.3C384,192,480,160,576,160C672,160,768,192,864,208C960,224,1056,224,1152,192C1248,160,1344,96,1392,64L1440,32L1440,320L0,320Z" />
        </svg>
      </div>

      <div className="max-w-md w-full space-y-8 bg-white p-10 rounded-xl shadow-2xl border border-slate-100 relative z-10">
        <div className="flex flex-col items-center">
          <div className="h-12 w-12 bg-teal-600 rounded-lg flex items-center justify-center">
            <Factory className="h-6 w-6 text-white" />
          </div>
          <h2 className="mt-6 text-center text-2xl font-extrabold text-slate-900">
            Sub Plant Portal
          </h2>
          <p className="mt-2 text-center text-sm text-slate-600">
            Sign in to manage your customers, orders and invoices
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          {error && (
            <div className="bg-red-50 text-red-600 p-3 rounded-lg text-sm border border-red-100">
              {error}
            </div>
          )}
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Email address</label>
              <Input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@subplant.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
              <Input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
              />
            </div>
          </div>

          <Button type="submit" className="w-full bg-teal-600 hover:bg-teal-700" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
          </Button>

          <p className="text-center text-xs text-slate-400">
            Accounts are created by FabricFlow. Contact your coordinator for access.
          </p>
        </form>
      </div>
    </div>
  );
}
