This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Component 3 monitoring

The Emergency Situation Detection & Management screen is available at
[http://localhost:3000/dashboard/monitoring](http://localhost:3000/dashboard/monitoring).

The screen contains both parts of Component 3:

- daily production and emergency-risk inputs;
- recovery-capacity inputs for workers, overtime, machines, repair time and a
  backup line;
- the recommended deadline-feasible action with its new completion date;
- expandable alternative recovery plans and calculation assumptions.

The recovery-capacity values in the demo presets are examples. Replace them
with the actual limits of the selected plant before using a recommendation.

Select **Enter current order** to clear the historical preset values and start
a present-day factory entry. The production date defaults to the browser's
current local Monday-Friday working date, using the most recent Friday when
opened on a weekend. Total working days are calculated automatically from the
approved date through the buyer-required date using an inclusive Monday-Friday
calendar. See
[`COMPONENT3_DEMO_GUIDE.md`](../COMPONENT3_DEMO_GUIDE.md) for the complete
demonstration sequence.

In current-order mode, **Cumulative completed** is read-only and calculated
automatically. On working day 1 it equals that day's actual output. From day 2
onward it equals the previous saved working day's cumulative quantity plus the
current actual output. Save each day before entering the next one; the screen
blocks calculation when the immediately preceding day is missing or when the
selected day is already saved.

For a currently stable day, the result also shows the three experimental
next-three-production-day warnings supported by Step 5C: machine breakdown,
quality-limit issue, and output/schedule risk. These uncalibrated scores use
only the current input and saved earlier records for the same order. They are
research-only, require manager review, and do not yet include a future
worker-shortage model. See
[`COMPONENT3_EARLY_WARNING_STEP5C.md`](../COMPONENT3_EARLY_WARNING_STEP5C.md).

After an analysis, use **Save & track incident** to create a persistent
workflow record. Open the Recovery History screen at
[http://localhost:3000/dashboard/recovery-history](http://localhost:3000/dashboard/recovery-history)
to approve an option, start the action, record actual output, review
effectiveness, and complete the incident.

Use **Save daily record** for every stable or emergency production day. The
Daily Monitoring History screen at
[http://localhost:3000/dashboard/monitoring-history](http://localhost:3000/dashboard/monitoring-history)
shows saved observations and lets a supervisor verify the actual stable or
emergency outcome. Three-day labels and training readiness use only those
verified actual outcomes; model detections remain visible for comparison.
Corrections create audit-history entries. Incident tracking remains a separate
action for emergency recovery approval and outcomes.

The Step 5A.3 card on Daily Monitoring History audits the verified training
export and enables CSV or Excel downloads when an eligible `Ready` row exists.
The Excel workbook includes the training table, audit evidence, and a column
role manifest.

The **Retrospective data loader** on the same page previews the original
Component 3 workbook, audits its Component 2 master-data matches, and imports
one order in chronological order. It requires explicit acknowledgement that
the workbook trained the current models. Optional automatic outcome
verification requires a second confirmation and reviewer identity. These
records demonstrate the workflow but are not new independent validation. See
[`COMPONENT3_HISTORICAL_IMPORT.md`](../COMPONENT3_HISTORICAL_IMPORT.md).
They remain visible in monitoring history but are automatically excluded from
independent readiness counts and the verified training export.

The **Step 5D.1 validation report** card compares the early-warning decision
saved before verification with its later verified three-day outcome. It shows
Accuracy, Macro-F1, and F1 for each target while keeping retrospective rows and
new unseen-order evidence in separate panels. See
[`COMPONENT3_EARLY_WARNING_STEP5D1.md`](../COMPONENT3_EARLY_WARNING_STEP5D1.md).

Copy the example environment file before starting the frontend:

```bash
cp .env.example .env.local
```

The default configuration expects the Component 3 Flask API at
`http://127.0.0.1:5001/api/component3`. Start that API from the repository root:

```bash
COMPONENT3_MODEL_VERSION=v2 python main.py
```

Set `NEXT_PUBLIC_COMPONENT3_API_URL` in `.env.local` when the backend uses a
different host, port, or deployment URL.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
