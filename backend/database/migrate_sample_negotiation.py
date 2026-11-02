"""
database/migrate_sample_negotiation.py

Idempotent migration that adds the columns needed for the sample-order
"request a new receive date" negotiation (mirrors the bulk timeline-email loop,
but driven by email replies).

  sample_orders:
    timeline_email_sent_at    when the date-request email was sent
    proposed_receive_date     the new receive date the admin proposed
    customer_response         'Approved' | 'Rejected' (buyer's reply intent)
    customer_message          free-text of the buyer's reply
    extension_days_requested  parsed "N days" if the buyer asked for more time
    customer_responded_at     when the reply was recorded

  inbound_emails:
    order_type                'bulk' | 'sample' — which table order_id points at

The sample status column keeps its original CHECK set ('Pending', ...), so the
negotiation sub-state is derived from these columns instead of a new status value.

Run:  python -m database.migrate_sample_negotiation   (from the garment_new dir)
"""
import os
import sqlite3


def _columns(db, table):
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}


def migrate(db_path=None):
    db_path = db_path or os.environ.get("DATABASE_PATH", "garment.db")
    db = sqlite3.connect(db_path)
    try:
        added = []

        sample_cols = _columns(db, "sample_orders")
        for name, decl in [
            ("timeline_email_sent_at", "DATETIME"),
            ("proposed_receive_date", "DATE"),
            ("customer_response", "TEXT"),
            ("customer_message", "TEXT"),
            ("extension_days_requested", "INTEGER"),
            ("customer_responded_at", "DATETIME"),
        ]:
            if name not in sample_cols:
                db.execute(f"ALTER TABLE sample_orders ADD COLUMN {name} {decl}")
                added.append(f"sample_orders.{name}")

        inbound_cols = _columns(db, "inbound_emails")
        if "order_type" not in inbound_cols:
            db.execute("ALTER TABLE inbound_emails ADD COLUMN order_type TEXT DEFAULT 'bulk'")
            added.append("inbound_emails.order_type")

        db.commit()
        if added:
            print("Added columns:", ", ".join(added))
        else:
            print("No changes — schema already up to date.")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
