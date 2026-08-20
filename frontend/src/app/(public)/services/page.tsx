import Link from "next/link";
import PageHero from "@/components/PageHero";
import {
  ClipboardList, Package, Gauge, BarChart3, ArrowRight, Sparkles,
  Ruler, Factory, Mail, ShieldCheck,
} from "lucide-react";

export const metadata = {
  title: "Our Services — FabricFlow",
  description: "Sample feasibility, bulk allocation, live monitoring and performance analysis for garment production.",
};

const SERVICES = [
  {
    icon: ClipboardList,
    title: "Sample Feasibility",
    tag: "Component 1",
    body: "Submit a style with your quantity and target date. Our first AI model predicts overrun risk, ranks every factory by suitability, and tells you instantly whether the sample is feasible — and where to make it.",
    points: ["Instant feasibility verdict", "Overrun-risk prediction", "Best-fit factory ranking", "Optional style-PDF upload"],
  },
  {
    icon: Package,
    title: "Bulk Order Allocation",
    tag: "Component 2",
    body: "Turn an approved sample into a production order. The allocation engine reads live monthly capacity across the network and assigns the plant best able to meet your delivery date.",
    points: ["Live capacity-aware allocation", "Production-day estimation", "Deadline feasibility check", "Plant recommendation with scores"],
  },
  {
    icon: Gauge,
    title: "Live Production Monitoring",
    tag: "Component 3",
    body: "Once production starts, daily logs are scanned for emerging risk — machine breakdowns, worker shortages, damage rates — so problems are flagged early enough to act on, not discovered at the deadline.",
    points: ["Daily risk scanning", "Early delay alerts", "Damage & downtime tracking", "Admin & plant notifications"],
  },
  {
    icon: BarChart3,
    title: "Performance Analysis",
    tag: "Component 4",
    body: "Every completed order is scored on how it actually ran. The result is a star rating and a ranked set of corrective recommendations that feed back into planning the next order.",
    points: ["Post-delivery scoring", "Star rating & performance score", "Ranked recommendations", "Continuous improvement loop"],
  },
];

const PROCESS = [
  { icon: Ruler, title: "Define", body: "Register and submit your style with specs, quantity and required date." },
  { icon: Sparkles, title: "Predict", body: "AI returns feasibility, the recommended plant and a timeline." },
  { icon: Factory, title: "Produce", body: "The order is assigned to a factory and tracked day by day." },
  { icon: ShieldCheck, title: "Deliver", body: "Completion is confirmed, shipped, and scored for next time." },
];

export default function ServicesPage() {
  return (
    <>
      <PageHero
        tone="blue"
        title="Everything you need to move from idea to delivery"
        subtitle="Four AI components working together across the full garment production lifecycle."
        crumbs={[{ name: "Our Services" }]}
      />

      {/* Service detail cards */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 py-16 space-y-6">
        {SERVICES.map((s, i) => (
          <div key={s.title} className={`grid md:grid-cols-2 gap-8 items-center rounded-3xl border border-slate-200 bg-white p-8 ${i % 2 ? "md:[&>div:first-child]:order-2" : ""}`}>
            <div>
              <div className="flex items-center gap-3 mb-3">
                <div className="w-11 h-11 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
                  <s.icon className="w-5 h-5" />
                </div>
                <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">{s.tag}</span>
              </div>
              <h2 className="text-2xl font-bold text-slate-900">{s.title}</h2>
              <p className="mt-3 text-slate-600 leading-relaxed">{s.body}</p>
            </div>
            <div className="bg-slate-50 rounded-2xl border border-slate-100 p-6">
              <ul className="space-y-3">
                {s.points.map((p) => (
                  <li key={p} className="flex items-center gap-3 text-sm text-slate-700">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-500" /> {p}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ))}
      </section>

      {/* Process */}
      <section className="bg-slate-50 border-y border-slate-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-16">
          <h2 className="text-3xl font-bold text-slate-900 text-center mb-12">How an order flows</h2>
          <div className="grid gap-6 md:grid-cols-4">
            {PROCESS.map((p) => (
              <div key={p.title} className="bg-white rounded-2xl border border-slate-200 p-6">
                <div className="w-11 h-11 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center mb-4">
                  <p.icon className="w-5 h-5" />
                </div>
                <h3 className="font-semibold text-slate-900">{p.title}</h3>
                <p className="text-sm text-slate-600 mt-1">{p.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 py-16">
        <div className="rounded-3xl bg-slate-900 text-white px-8 py-12 flex flex-col md:flex-row items-center justify-between gap-6">
          <div>
            <h2 className="text-2xl font-bold">Start with a single sample request</h2>
            <p className="text-slate-300 mt-2">See feasibility and the best factory in seconds.</p>
          </div>
          <div className="flex gap-3 shrink-0">
            <Link href="/register" className="px-6 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold inline-flex items-center gap-2 transition-colors">
              Get started <ArrowRight className="w-4 h-4" />
            </Link>
            <Link href="/contact" className="px-6 py-3 bg-white/10 hover:bg-white/20 rounded-lg font-semibold inline-flex items-center gap-2 transition-colors">
              <Mail className="w-4 h-4" /> Contact
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
