"use client";

import { useState } from "react";
import Swal from "@/lib/swal";
import api from "@/lib/api";
import PageHero from "@/components/PageHero";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Mail, MapPin, MessageSquare, Clock, Phone } from "lucide-react";

export default function ContactPage() {
  const [form, setForm] = useState({ name: "", email: "", subject: "", message: "" });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim() || !form.email.trim() || !form.message.trim()) {
      Swal.fire({ icon: "warning", title: "Please fill in your name, email and message." });
      return;
    }
    setSubmitting(true);
    try {
      await api.post("/public/contact", form);
      Swal.fire({ icon: "success", title: "Message sent", text: "Thanks for reaching out — we'll get back to you soon." });
      setForm({ name: "", email: "", subject: "", message: "" });
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to send message." });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <PageHero
        tone="sky"
        title="Contact Us"
        subtitle="Questions about an order or partnering with FabricFlow? The team will get back to you within one business day."
        crumbs={[{ name: "Contact Us" }]}
      />

      <section className="max-w-5xl mx-auto px-4 sm:px-6 py-16 grid gap-10 md:grid-cols-5">
        {/* Info */}
        <div className="md:col-span-2 space-y-6">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
              <Mail className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900">Email</h3>
              <p className="text-sm text-slate-600">admin@fabricflow.com</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
              <MapPin className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900">Head office</h3>
              <p className="text-sm text-slate-600">FabricFlow International, Colombo, Sri Lanka</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
              <Phone className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900">Phone</h3>
              <p className="text-sm text-slate-600">+94 11 000 0000</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900">Business hours</h3>
              <p className="text-sm text-slate-600">Mon–Fri, 9:00–18:00 (GMT+5:30)</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
              <MessageSquare className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900">Response time</h3>
              <p className="text-sm text-slate-600">We typically reply within one business day.</p>
            </div>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="md:col-span-3 bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Name *</label>
              <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Your name" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Email *</label>
              <Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="you@company.com" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Subject</label>
            <Input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} placeholder="How can we help?" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Message *</label>
            <textarea
              required
              rows={5}
              value={form.message}
              onChange={(e) => setForm({ ...form, message: e.target.value })}
              placeholder="Tell us a bit more..."
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-950"
            />
          </div>
          <Button type="submit" disabled={submitting} className="w-full bg-blue-600 hover:bg-blue-700">
            {submitting ? "Sending..." : "Send message"}
          </Button>
        </form>
      </section>
    </>
  );
}
