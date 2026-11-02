// Public marketing home — owns the "/" route via the (public) route group.
import Link from "next/link";
import {
  ClipboardList, Package, BarChart3, Gauge, ArrowRight, Sparkles, ShieldCheck,
  Factory, Cpu, Clock, CheckCircle2, TrendingUp, Star, Quote,
} from "lucide-react";

export const metadata = {
  title: "FabricFlow — AI-Driven Garment Production",
  description: "Sample feasibility, bulk allocation, and live production intelligence for garment manufacturing.",
};

const STATS = [
  { value: "6", label: "Partner factories" },
  { value: "4", label: "AI decision models" },
  { value: "98%", label: "On-time visibility" },
  { value: "24/7", label: "Live monitoring" },
];

const SERVICES = [
  { icon: ClipboardList, title: "Sample Feasibility", body: "Submit a style and get an instant AI read on overrun risk and the best factory, from live capacity." },
  { icon: Package, title: "Bulk Allocation", body: "Place large orders and let the engine allocate them to the optimal plants to hit your delivery date." },
  { icon: Gauge, title: "Live Monitoring", body: "Daily logs are scanned for emerging risks so delays are caught early, not at the deadline." },
  { icon: BarChart3, title: "Performance Analysis", body: "Every completed order is scored, turning factory performance into ranked, actionable recommendations." },
];

const STEPS = [
  { n: "01", title: "Request a sample", body: "Upload your style, quantity and target date." },
  { n: "02", title: "Get an AI read", body: "Feasibility and the recommended plant in seconds." },
  { n: "03", title: "Place the bulk order", body: "We allocate it across the network for you." },
  { n: "04", title: "Track to delivery", body: "Live monitoring right through to shipment." },
];

const FEATURES = [
  { icon: Cpu, title: "Grounded in data", body: "Predictions run on trained models and live utilisation — not guesswork." },
  { icon: Clock, title: "Deadlines protected", body: "Overrun and capacity risks surface early enough to act on them." },
  { icon: Factory, title: "One network", body: "Buyers, the mother company and every plant see the same picture." },
  { icon: ShieldCheck, title: "Transparent workflow", body: "From feasibility to shipment, each step is tracked and auditable." },
];

const FAQS = [
  { q: "How fast is a feasibility result?", a: "Sample feasibility and the recommended plant are returned within seconds of submitting a request." },
  { q: "Can one order use multiple factories?", a: "Yes — bulk orders are allocated to the plant best suited to meet your date, drawn from live capacity." },
  { q: "How do I get an account?", a: "Register a buyer account; it's activated once the mother company approves it, then you can submit orders." },
  { q: "Are my style files kept private?", a: "Uploaded style files are stored securely and served only to authorised users on your order." },
];

export default function PublicHome() {
  return (
    <>
      {/* Hero — rounded, side-spaced, image on the right */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 pt-6">
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 to-slate-800">
          <div className="grid md:grid-cols-2 items-center gap-8 px-6 sm:px-12 py-12 md:py-16">
            <div className="relative z-10">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 text-blue-200 text-xs font-medium mb-6">
                <Sparkles className="w-3.5 h-3.5" /> AI-driven production decisions
              </div>
              <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight text-white leading-tight">
                Smarter garment production, from sample to shipment.
              </h1>
              <p className="mt-5 text-lg text-slate-300 max-w-md">
                FabricFlow connects buyers with our factory network and uses AI to predict
                feasibility, allocate capacity, and keep every order on schedule.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link href="/register" className="px-6 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold text-white transition-colors inline-flex items-center gap-2">
                  Get started <ArrowRight className="w-4 h-4" />
                </Link>
                <Link href="/services" className="px-6 py-3 bg-white/10 hover:bg-white/20 rounded-lg font-semibold text-white transition-colors">
                  Our services
                </Link>
              </div>
            </div>
            <div className="relative">
              <img src="/hero-apparel.svg" alt="Garment apparel illustration" className="w-full max-w-md mx-auto drop-shadow-2xl" />
            </div>
          </div>
        </div>
      </section>

      {/* Stats bar */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 mt-10">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {STATS.map((s) => (
            <div key={s.label} className="bg-white rounded-2xl border border-slate-200 p-5 text-center">
              <p className="text-3xl font-extrabold text-slate-900">{s.value}</p>
              <p className="text-sm text-slate-500 mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Services */}
      <section id="services" className="max-w-6xl mx-auto px-4 sm:px-6 py-20 scroll-mt-16">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <h2 className="text-3xl font-bold text-slate-900">What we do</h2>
          <p className="mt-3 text-slate-600">An end-to-end platform covering the full production lifecycle.</p>
        </div>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {SERVICES.map((s) => (
            <div key={s.title} className="p-6 rounded-2xl border border-slate-200 bg-white hover:shadow-md transition-shadow">
              <div className="w-11 h-11 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center mb-4">
                <s.icon className="w-5 h-5" />
              </div>
              <h3 className="font-semibold text-slate-900 mb-2">{s.title}</h3>
              <p className="text-sm text-slate-600 leading-relaxed">{s.body}</p>
            </div>
          ))}
        </div>
        <div className="text-center mt-8">
          <Link href="/services" className="inline-flex items-center gap-2 text-blue-600 font-medium hover:text-blue-700">
            Explore all services <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>

      {/* How it works */}
      <section className="bg-slate-50 border-y border-slate-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-20">
          <h2 className="text-3xl font-bold text-slate-900 text-center mb-12">How it works</h2>
          <div className="grid gap-6 md:grid-cols-4">
            {STEPS.map((step) => (
              <div key={step.n} className="relative">
                <div className="text-4xl font-extrabold text-blue-100">{step.n}</div>
                <h3 className="font-semibold text-slate-900 mt-2">{step.title}</h3>
                <p className="text-sm text-slate-600 mt-1">{step.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Why choose us */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 py-20">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div>
            <h2 className="text-3xl font-bold text-slate-900">Why buyers choose FabricFlow</h2>
            <p className="mt-3 text-slate-600">
              Traditional sourcing runs on spreadsheets and best-effort estimates. We replace
              that with a transparent, data-backed workflow that everyone can see.
            </p>
            <div className="mt-8 grid sm:grid-cols-2 gap-6">
              {FEATURES.map((f) => (
                <div key={f.title} className="flex gap-3">
                  <div className="w-10 h-10 rounded-lg bg-slate-900 text-white flex items-center justify-center shrink-0">
                    <f.icon className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-slate-900">{f.title}</h3>
                    <p className="text-sm text-slate-600 mt-0.5">{f.body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-3xl bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-100 p-8">
            <div className="space-y-4">
              {[
                { icon: CheckCircle2, text: "Instant sample feasibility with the best-fit factory" },
                { icon: TrendingUp, text: "Bulk allocation optimised against live capacity" },
                { icon: Gauge, text: "Daily production risk detection" },
                { icon: BarChart3, text: "Post-delivery performance scoring" },
              ].map((row) => (
                <div key={row.text} className="flex items-center gap-3 bg-white rounded-xl border border-slate-200 px-4 py-3">
                  <row.icon className="w-5 h-5 text-blue-600 shrink-0" />
                  <span className="text-sm text-slate-700">{row.text}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Testimonial */}
      <section className="bg-slate-900 text-white">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-20 text-center">
          <div className="flex justify-center gap-1 mb-5">
            {[...Array(5)].map((_, i) => <Star key={i} className="w-5 h-5 text-amber-400 fill-amber-400" />)}
          </div>
          <Quote className="w-10 h-10 text-white/20 mx-auto mb-4" />
          <p className="text-xl md:text-2xl font-medium leading-relaxed">
            "We used to chase feasibility over email for days. Now we submit a style and get a
            clear answer — and the right factory — before the call even ends."
          </p>
          <p className="mt-6 text-slate-400 text-sm">A wholesale apparel buyer on the FabricFlow network</p>
        </div>
      </section>

      {/* FAQ */}
      <section className="max-w-4xl mx-auto px-4 sm:px-6 py-20">
        <h2 className="text-3xl font-bold text-slate-900 text-center mb-10">Frequently asked</h2>
        <div className="space-y-4">
          {FAQS.map((f) => (
            <div key={f.q} className="rounded-2xl border border-slate-200 bg-white p-6">
              <h3 className="font-semibold text-slate-900">{f.q}</h3>
              <p className="text-sm text-slate-600 mt-2 leading-relaxed">{f.a}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 pb-20">
        <div className="rounded-3xl bg-slate-900 text-white px-8 py-14 text-center relative overflow-hidden">
          <ShieldCheck className="w-12 h-12 text-blue-400 mx-auto mb-4" />
          <h2 className="text-3xl font-bold">Ready to produce smarter?</h2>
          <p className="mt-3 text-slate-300 max-w-xl mx-auto">
            Register a buyer account and submit your first sample request today.
          </p>
          <div className="mt-8 flex flex-wrap gap-3 justify-center">
            <Link href="/register" className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold transition-colors">
              Create an account <ArrowRight className="w-4 h-4" />
            </Link>
            <Link href="/contact" className="inline-flex items-center gap-2 px-6 py-3 bg-white/10 hover:bg-white/20 rounded-lg font-semibold transition-colors">
              Talk to us
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
