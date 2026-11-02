import PageHero from "@/components/PageHero";

export const metadata = {
  title: "Privacy Policy — FabricFlow",
  description: "How FabricFlow collects, uses, and protects your information.",
};

const SECTIONS = [
  {
    h: "1. Information we collect",
    p: "When you register a buyer account we collect your company name, contact person, email address, and the contact and identification details you provide (such as contact number, country, and address). When you place sample or bulk orders we collect the order details, uploaded style files, and production data associated with those orders.",
  },
  {
    h: "2. How we use your information",
    p: "We use your information to operate the platform: to authenticate you, process and allocate your orders, run feasibility and production analyses, notify you of order status, and communicate with you about your account. Order and production data is shared with the assigned factory only to the extent needed to fulfil your order.",
  },
  {
    h: "3. Data sharing",
    p: "We do not sell your personal information. Information is shared with the mother company and the specific plant assigned to your order for fulfilment purposes. We may share information where required by law.",
  },
  {
    h: "4. Data security",
    p: "Access to your account is protected by authentication and role-based permissions. Uploaded files are stored on our servers and served only to authorised users. While we take reasonable measures to protect your data, no method of transmission or storage is completely secure.",
  },
  {
    h: "5. Data retention",
    p: "We retain your account and order information for as long as your account is active and as needed to provide the service, comply with legal obligations, resolve disputes, and enforce our agreements.",
  },
  {
    h: "6. Your rights",
    p: "You may request access to, correction of, or deletion of your personal information by contacting us through the Contact Us page. Some information may be retained where we have a legal basis or obligation to do so.",
  },
  {
    h: "7. Changes to this policy",
    p: "We may update this Privacy Policy from time to time. Material changes will be reflected on this page with an updated effective date.",
  },
];

export default function PrivacyPage() {
  return (
    <>
      <PageHero
        tone="slate"
        title="Privacy Policy"
        subtitle={`How FabricFlow collects, uses, and protects your information. Last updated ${new Date().getFullYear()}.`}
        crumbs={[{ name: "Privacy Policy" }]}
      />
    <section className="max-w-3xl mx-auto px-4 sm:px-6 py-16">
      <div className="space-y-8">
        {SECTIONS.map((s) => (
          <div key={s.h}>
            <h2 className="text-lg font-semibold text-slate-900 mb-2">{s.h}</h2>
            <p className="text-slate-600 leading-relaxed">{s.p}</p>
          </div>
        ))}
      </div>
    </section>
    </>
  );
}
