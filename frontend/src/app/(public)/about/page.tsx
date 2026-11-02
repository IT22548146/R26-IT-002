import PageHero from "@/components/PageHero";
import { Target, Users, Cpu, Factory, ShieldCheck, TrendingUp } from "lucide-react";

export const metadata = {
  title: "About Us — FabricFlow",
  description: "Who we are and how FabricFlow brings AI to garment production.",
};

const VALUES = [
  { icon: Target, title: "Reliability", body: "Delivery dates are commitments. Our models exist to protect them." },
  { icon: Cpu, title: "Intelligence", body: "Decisions are grounded in live capacity data and trained models, not guesswork." },
  { icon: Users, title: "Partnership", body: "We connect buyers and factories on one transparent platform." },
];

const STATS = [
  { value: "6", label: "Partner factories" },
  { value: "4", label: "AI models in production" },
  { value: "1", label: "Unified workflow" },
];

export default function AboutPage() {
  return (
    <>
      <PageHero
        tone="indigo"
        title="Bringing intelligence to garment manufacturing"
        subtitle="FabricFlow links garment buyers with a network of specialist factories — coordinated by AI."
        crumbs={[{ name: "About Us" }]}
      />

      {/* Intro */}
      <section className="max-w-4xl mx-auto px-4 sm:px-6 py-16 space-y-6 text-slate-700 leading-relaxed">
        <p>
          Traditional garment sourcing runs on spreadsheets, phone calls, and best-effort
          estimates. Feasibility is a guess, capacity is opaque, and problems surface only
          when a deadline is already missed.
        </p>
        <p>
          We built FabricFlow to change that. When a buyer submits a sample or a bulk order,
          the platform predicts whether it can be met, recommends the best factory based on
          live utilisation and historical performance, and then monitors production day by
          day so risks are flagged early enough to act on.
        </p>
        <p>
          The result is a single, transparent workflow where buyers, the mother company, and
          each plant see the same picture — and every completed order feeds back into the
          models that plan the next one.
        </p>
      </section>

      {/* Stats */}
      <section className="max-w-5xl mx-auto px-4 sm:px-6 pb-4">
        <div className="grid grid-cols-3 gap-4">
          {STATS.map((s) => (
            <div key={s.label} className="bg-white rounded-2xl border border-slate-200 p-6 text-center">
              <p className="text-3xl font-extrabold text-slate-900">{s.value}</p>
              <p className="text-sm text-slate-500 mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Mission / approach */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 py-16 grid lg:grid-cols-2 gap-10 items-center">
        <div className="rounded-3xl bg-gradient-to-br from-indigo-50 to-blue-50 border border-indigo-100 p-8 space-y-4">
          {[
            { icon: Factory, text: "A coordinated network of specialist embroidery and manufacturing plants." },
            { icon: TrendingUp, text: "Allocation driven by live capacity and historical on-time performance." },
            { icon: ShieldCheck, text: "Every order tracked end to end, from feasibility to shipment." },
          ].map((row) => (
            <div key={row.text} className="flex items-center gap-3 bg-white rounded-xl border border-slate-200 px-4 py-3">
              <row.icon className="w-5 h-5 text-indigo-600 shrink-0" />
              <span className="text-sm text-slate-700">{row.text}</span>
            </div>
          ))}
        </div>
        <div>
          <h2 className="text-3xl font-bold text-slate-900">Our approach</h2>
          <p className="mt-3 text-slate-600 leading-relaxed">
            Each AI component owns one decision — feasibility, allocation, risk detection,
            and performance analysis — and together they form a closed loop. Data from
            finished orders continuously sharpens the predictions that plan new ones, so the
            platform gets more accurate the more it is used.
          </p>
        </div>
      </section>

      {/* Values */}
      <section className="bg-slate-50 border-y border-slate-200">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-16">
          <h2 className="text-2xl font-bold text-slate-900 text-center mb-10">What we value</h2>
          <div className="grid gap-6 md:grid-cols-3">
            {VALUES.map((v) => (
              <div key={v.title} className="p-6 rounded-2xl bg-white border border-slate-200">
                <div className="w-11 h-11 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center mb-4">
                  <v.icon className="w-5 h-5" />
                </div>
                <h3 className="font-semibold text-slate-900 mb-2">{v.title}</h3>
                <p className="text-sm text-slate-600">{v.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
