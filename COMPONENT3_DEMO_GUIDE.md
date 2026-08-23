# Component 3 Demonstration Guide

This guide presents the complete Emergency Situation Detection and Management
workflow without claiming that the research-only early-warning artifacts are
already production approved.

## 1. Start the application

From the repository root, start the Component 3 Flask API:

```bash
COMPONENT3_MODEL_VERSION=v2 python main.py
```

In a second terminal, start the frontend:

```bash
cd frontends
npm run dev
```

Open `http://localhost:3000/dashboard/monitoring`.

## 2. Demonstrate current monitoring

The five historical presets provide repeatable examples:

1. **Healthy line** shows the distinction between a stable current day and any
   separate delivery or future-warning exposure.
2. **Worker pressure** detects a worker shortage and compares additional-worker
   and overtime recovery options.
3. **Machine event** demonstrates repair and backup-machine recovery capacity.
4. **Quality pressure** demonstrates a breached damage limit.
5. **Critical delay** demonstrates deadline escalation and alternative
   capacity.

Choose a preset and select **Analyse risk & build recovery plan**. The result
separates:

- the current-day operational situation;
- the order-delivery outlook;
- experimental next-three-production-day warnings; and
- the executable recovery recommendation and alternatives.

Changing any order, production, timeline, or recovery input clears the old
result. Run the analysis again to avoid presenting a stale decision.

## 3. Demonstrate a present-day order

Select **Enter current order**. The form clears historical order values, sets
the production date to the current local Monday-Friday working date (or the
most recent Friday when opened on a weekend), and leaves actual order and
plant-capacity fields for entry. The total working days are calculated from the
approved date through the buyer-required date using an inclusive Monday-Friday
calendar.

The form and API reject:

- a buyer-required date before approval;
- a production date outside the approved-to-required interval;
- a Saturday or Sunday production date under the current calendar rule;
- cutting or sewing days longer than the total schedule; and
- a current working-day number outside the order schedule.

Public holidays and factory-specific Saturday shifts are not currently
subtracted automatically.

## 4. Demonstrate persistence and recovery tracking

After analysis:

1. enter the recorder identity and select **Save daily record**;
2. for an operational or schedule recovery case, select
   **Save & track incident**;
3. open Recovery History;
4. approve a recovery option, start it, record actual output, review its
   effectiveness, and complete the case.

## 5. Prepare monitoring-history evidence

Select **Prepare demo history**, or open
`http://localhost:3000/dashboard/monitoring-history#historical-import`.

Import and verify BULK0007 once using the Retrospective Data Loader. The local
SQLite database is not committed to Git, so this setup must be repeated on a
new demonstration computer. The resulting Step 5D.1 card shows Accuracy,
Macro-F1, and F1 while clearly separating retrospective training-data reuse
from independent validation.

## Evidence statement

The recommended presentation wording is:

> Component 3 is an executable end-to-end research system for emergency
> detection, early warning, recovery planning, and outcome tracking. Its
> historical demonstration evidence is separated from future independent
> production validation.
