"""
services/inbound_email_service.py
IMAP polling: read customer replies to the completion-timeline emails and fold
them back into the system, matched to a bulk order by the [Order #N] subject.

Config (env):
  IMAP_HOST      default imap.gmail.com
  IMAP_PORT      default 993
  IMAP_USER      mailbox address (same account that sends, usually)
  IMAP_PASSWORD  app password (Gmail requires an App Password, not the login one)
  IMAP_MAILBOX   default INBOX
  INBOUND_POLL_SECONDS   background poll interval (default 120; 0 disables the thread)

Design notes:
  * Uses its own sqlite connection (no Flask request context needed), so the
    same function works from a manual endpoint or a background thread.
  * Auto-applies a reply ONLY when the intent is clear AND the sender matches
    the order's buyer. Anything ambiguous is logged and left for the admin to
    action manually — we never guess a status change.
"""

import os
import re
import email
import imaplib
import sqlite3
from datetime import datetime
from email.header import decode_header


def _cfg():
    return {
        "host": os.environ.get("IMAP_HOST", "imap.gmail.com"),
        "port": int(os.environ.get("IMAP_PORT", 993)),
        "user": os.environ.get("IMAP_USER", ""),
        "password": os.environ.get("IMAP_PASSWORD", ""),
        "mailbox": os.environ.get("IMAP_MAILBOX", "INBOX"),
    }


def is_configured() -> bool:
    c = _cfg()
    return bool(c["user"] and c["password"])


def _db():
    path = os.environ.get("DATABASE_PATH", "garment.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _decode(value) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = ""
    for text, enc in parts:
        if isinstance(text, bytes):
            try:
                out += text.decode(enc or "utf-8", "replace")
            except Exception:
                out += text.decode("utf-8", "replace")
        else:
            out += text
    return out


def _plain_body(msg) -> str:
    """Extract the text/plain body (fall back to any text)."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition")):
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                except Exception:
                    continue
        # fall back to any text
        for part in msg.walk():
            if part.get_content_type().startswith("text/"):
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                except Exception:
                    continue
        return ""
    try:
        return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "replace")
    except Exception:
        return str(msg.get_payload())


def _reply_only(body: str) -> str:
    """Trim quoted history so keyword detection reads the customer's new text."""
    lines = []
    for ln in body.splitlines():
        s = ln.strip()
        if s.startswith(">"):
            break
        if re.match(r"^On .+ wrote:$", s):
            break
        if s.lower().startswith("from:") and lines:
            break
        lines.append(ln)
    return "\n".join(lines).strip() or body.strip()


ORDER_RE = re.compile(r"order\s*#?\s*(\d+)", re.IGNORECASE)
SAMPLE_RE = re.compile(r"sample\s*#?\s*(\d+)", re.IGNORECASE)
DAYS_RE = re.compile(r"(\d+)\s*(?:more\s*|extra\s*|additional\s*)?days?", re.IGNORECASE)

# Strong approvals are unambiguous; weak ones ("accept", "yes") can collide with
# negations like "cannot accept", so a reject signal overrides them.
STRONG_APPROVE = ("approve", "approved", "go ahead", "proceed", "we agree", "agreed",
                  "confirmed", "happy to proceed", "please proceed")
WEAK_APPROVE = ("accept", "yes")
REJECT_WORDS = ("extend", "extension", "more time", "more days", "additional days",
                "cannot", "can't", "unable", "decline", "reject", "not able", "won't be able")


def _detect(text: str):
    """Return (action, extension_days). action in Approved/Rejected/Unclear."""
    low = text.lower()
    wants_more = any(w in low for w in REJECT_WORDS)
    strong = any(w in low for w in STRONG_APPROVE)
    weak = any(w in low for w in WEAK_APPROVE)

    days = None
    m = DAYS_RE.search(text)
    if m:
        days = int(m.group(1))

    if wants_more:
        # An extension request wins unless a strong approval is also present
        # (contradictory → leave for manual review).
        return ("Unclear", days) if strong else ("Rejected", days)
    if strong or weak:
        return "Approved", None
    return "Unclear", days


def _notify_admin_reply(conn, related_type, order_id, label, action, days):
    """Insert an admin notification about a customer's emailed reply (no Flask ctx)."""
    admin = conn.execute("SELECT id FROM users WHERE role='Admin' LIMIT 1").fetchone()
    if not admin:
        return
    extra = f" and requested +{days} day(s)" if (action == "Rejected" and days) else ""
    conn.execute(
        """INSERT INTO notifications
           (user_id, title, message, type, related_order_type, related_order_id)
           VALUES (?,?,?,?,?,?)""",
        (admin["id"], f"Email Reply — {label} #{order_id}",
         f"Customer emailed a reply: {action}{extra}.",
         "info", related_type, order_id),
    )


def poll_inbox() -> dict:
    """
    Fetch unseen mail, match to bulk + sample orders, apply clear replies, log
    everything. Returns a summary dict.
    """
    if not is_configured():
        return {"configured": False, "fetched": 0, "matched": 0, "applied": 0,
                "message": "IMAP is not configured (set IMAP_USER / IMAP_PASSWORD)."}

    c = _cfg()
    fetched = matched = applied = 0
    conn = _db()
    try:
        imap = imaplib.IMAP4_SSL(c["host"], c["port"])
        imap.login(c["user"], c["password"])
        imap.select(c["mailbox"])
        # Narrow server-side to unseen replies to OUR threads. Bulk timeline emails
        # end with "...Within Timeline"; sample date-request emails carry "Receive
        # Date". These phrases match our threads (and their "Re:" replies) but not
        # unrelated mail. Combine the UID sets, keeping order and de-duplicating.
        uids, seen_uids = [], set()
        for phrase in ("Within Timeline", "Receive Date"):
            typ, data = imap.uid("search", None, f'(UNSEEN SUBJECT "{phrase}")')
            for u in (data[0].split() if typ == "OK" and data and data[0] else []):
                if u not in seen_uids:
                    seen_uids.add(u)
                    uids.append(u)

        for uid in uids:
            uid_str = uid.decode()
            # Skip if we've already stored this UID.
            if conn.execute("SELECT 1 FROM inbound_emails WHERE message_uid=?", (uid_str,)).fetchone():
                continue

            # BODY.PEEK reads WITHOUT setting the \Seen flag — we only mark an
            # email read once we've confirmed it's a reply to one of our orders.
            typ, msg_data = imap.uid("fetch", uid, "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            subject = _decode(msg.get("Subject"))
            subj_low = subject.lower()

            # Route by our subject tag: "[Sample #N]" -> sample order,
            # "[Order #N]" -> bulk order. Anything else is left untouched (unread).
            if "[sample #" in subj_low:
                order_type, table, m = "sample", "sample_orders", SAMPLE_RE.search(subject)
            elif "[order #" in subj_low:
                order_type, table, m = "bulk", "bulk_orders", ORDER_RE.search(subject)
            else:
                continue
            order_id = int(m.group(1)) if m else None
            order = conn.execute(f"SELECT * FROM {table} WHERE id=?", (order_id,)).fetchone() if order_id else None
            if not order:
                continue  # not one of ours — do not read, do not log

            from_addr = email.utils.parseaddr(msg.get("From"))[1].lower()
            # Ignore our own sent copies — we only care about the buyer's reply.
            if from_addr == c["user"].lower():
                continue

            fetched += 1
            body_full = _plain_body(msg)
            body = _reply_only(body_full)
            action, days = _detect(body)

            note = None
            did_apply = 0
            buyer = conn.execute("SELECT id, email FROM users WHERE id=?", (order["buyer_id"],)).fetchone()
            buyer_email = (buyer["email"] or "").lower() if buyer else ""

            if buyer_email and from_addr and from_addr != buyer_email:
                note = f"Sender {from_addr} is not the order's buyer — logged for review."
            elif action == "Unclear":
                note = "Reply intent unclear — left for manual review."
            elif order_type == "bulk":
                if order["status"] != "CustomerPending":
                    note = f"Order is '{order['status']}', not awaiting a reply — logged only."
                else:
                    matched += 1
                    new_status = "CustomerPending" if action == "Approved" else "Hold"
                    conn.execute(
                        """UPDATE bulk_orders
                           SET customer_response=?, status=?, customer_message=?,
                               extension_days_requested=?, customer_responded_at=?
                           WHERE id=?""",
                        (action, new_status, body[:1000], days, datetime.utcnow(), order_id),
                    )
                    did_apply = 1
                    applied += 1
                    _notify_admin_reply(conn, "bulk_order", order_id, "Bulk Order", action, days)
            else:  # sample
                # Awaiting the buyer only after we've sent the date-request email
                # and no reply is recorded yet. Status stays 'Pending' throughout.
                if not order["timeline_email_sent_at"] or order["customer_response"]:
                    note = "Sample order is not awaiting a date reply — logged only."
                else:
                    matched += 1
                    conn.execute(
                        """UPDATE sample_orders
                           SET customer_response=?, customer_message=?,
                               extension_days_requested=?, customer_responded_at=?
                           WHERE id=?""",
                        (action, body[:1000], days, datetime.utcnow(), order_id),
                    )
                    did_apply = 1
                    applied += 1
                    _notify_admin_reply(conn, "sample_order", order_id, "Sample Order", action, days)

            conn.execute(
                """INSERT INTO inbound_emails
                   (message_uid, order_id, order_type, from_addr, subject, body,
                    detected_action, extension_days, applied, note)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (uid_str, order_id, order_type, from_addr, subject, body[:4000], action, days, did_apply, note),
            )
            conn.commit()
            # Mark as read so it isn't re-fetched.
            imap.uid("store", uid, "+FLAGS", "(\\Seen)")

        imap.logout()
        return {"configured": True, "fetched": fetched, "matched": matched, "applied": applied,
                "message": f"Checked inbox: {fetched} new, {applied} applied to orders."}
    except imaplib.IMAP4.error as exc:
        return {"configured": True, "fetched": fetched, "matched": matched, "applied": applied,
                "error": f"IMAP login/fetch failed: {exc}"}
    except Exception as exc:
        return {"configured": True, "fetched": fetched, "matched": matched, "applied": applied,
                "error": f"Inbox poll failed: {exc}"}
    finally:
        conn.close()
