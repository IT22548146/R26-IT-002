"""
database/seed_plant_performance.py

Seeds realistic historical plant operations data for Component 4 (plant-based).

Generates, for each plant and each working day over the last N months:
  * plant_daily_logs — machines active, staff present, breakdowns, shortages,
    output and damage.

Each plant is given a distinct "character" (efficiency, reliability, damage
tendency) derived from its real KPI columns, so the resulting rankings are
meaningful rather than random noise. All values are kept inside Component 4's
training ranges so predictions stay valid.

Idempotent: re-running replaces the seeded window (INSERT OR REPLACE on the
plant_id + log_date unique key).

Run:  python -m database.seed_plant_performance [months]
"""
import os
import random
import sqlite3
import sys
from datetime import date, timedelta

MONTHS_DEFAULT = 6
SEED = 20260826  # fixed so runs are reproducible

# Per-plant character: (output_factor, breakdown_chance, shortage_chance, damage_pct_base)
# Tuned so PL01 is the strongest performer and PL06 the weakest, matching the
# quality_rating / historical_on_time_rate already stored on each plant.
PLANT_PROFILE = {
    "PL01": (1.00, 0.06, 0.05, 2.0),
    "PL02": (0.93, 0.10, 0.08, 2.5),
    "PL03": (0.88, 0.12, 0.10, 2.8),
    "PL04": (0.84, 0.15, 0.12, 3.1),
    "PL05": (0.90, 0.11, 0.09, 2.6),
    "PL06": (0.80, 0.18, 0.15, 3.6),
}
DEFAULT_PROFILE = (0.85, 0.12, 0.10, 2.9)


def _db():
    return sqlite3.connect(os.environ.get("DATABASE_PATH", "garment.db"))


def seed(months: int = MONTHS_DEFAULT):
    rnd = random.Random(SEED)
    conn = _db()
    conn.row_factory = sqlite3.Row
    plants = conn.execute("SELECT * FROM plants ORDER BY id").fetchall()
    if not plants:
        print("No plants found — seed plants first.")
        return

    today = date.today()
    start = today - timedelta(days=months * 30)
    rows = 0

    for p in plants:
        prof = PLANT_PROFILE.get(p["id"], DEFAULT_PROFILE)
        out_factor, brk_chance, short_chance, dmg_base = prof
        machines = p["total_machines"] or 16
        employees = p["employee_count"] or 45
        # Base daily output scaled by machines and the plant's efficiency character.
        base_output = machines * 28 * out_factor

        d = start
        while d <= today:
            # Skip Sundays — single weekly rest day (typical garment plant).
            if d.weekday() == 6:
                d += timedelta(days=1)
                continue

            breakdowns = rnd.randint(1, 3) if rnd.random() < brk_chance else 0
            shortages = rnd.randint(1, 4) if rnd.random() < short_chance else 0

            # Active machines = total minus breakdowns minus routine idle
            # (maintenance, changeover, no work loaded). Idle scales with the
            # plant's character so utilisation becomes a real differentiator.
            idle_ceiling = max(1, int(machines * (1.0 - out_factor) * 1.6) + 1)
            idle = rnd.randint(0, idle_ceiling)
            machines_active = max(int(machines * 0.62), machines - breakdowns - idle)
            employees_present = max(int(employees * 0.70), employees - shortages * 2)

            # Output tracks machine availability, with day-to-day variance, and
            # takes a hit when staff are short.
            util = machines_active / machines
            noise = rnd.uniform(0.88, 1.12)
            output = int(base_output * util * noise * (0.93 if shortages else 1.0))
            output = max(90, output)  # stay above C4's daily_output_avg floor

            # Damage rises with disruption; keep it in a believable band.
            dmg_pct = dmg_base + (0.35 if breakdowns else 0) + (0.25 if shortages else 0)
            dmg_pct = max(0.8, min(4.4, dmg_pct + rnd.uniform(-0.5, 0.5)))
            damage_qty = max(0, int(output * dmg_pct / 100))

            urgent = 1 if rnd.random() < 0.18 else 0

            conn.execute(
                """INSERT OR REPLACE INTO plant_daily_logs
                   (plant_id, log_date, machines_total, machines_active, employees_present,
                    machine_breakdown_count, worker_shortage_count, total_output,
                    total_damage_qty, urgent_orders_handled, notes, submitted_by)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (p["id"], d.isoformat(), machines, machines_active, employees_present,
                 breakdowns, shortages, output, damage_qty, urgent, "seeded", None),
            )
            rows += 1
            d += timedelta(days=1)

    conn.commit()
    total = conn.execute("SELECT COUNT(*) c FROM plant_daily_logs").fetchone()["c"]
    print(f"Seeded {rows} plant-day rows across {len(plants)} plants "
          f"({months} months). plant_daily_logs total: {total}")
    conn.close()


if __name__ == "__main__":
    seed(int(sys.argv[1]) if len(sys.argv) > 1 else MONTHS_DEFAULT)
