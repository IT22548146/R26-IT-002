"""
services/email_service.py
Gmail SMTP email utility for the Garment Production System.
All email templates are defined here.
"""

import os
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Seconds to wait on the SMTP socket. Without this, a slow or unreachable mail
# server can hang a request for minutes (the OS default can be very long).
SMTP_TIMEOUT = int(os.environ.get("SMTP_TIMEOUT", 15))

# Emails are dispatched on a background thread so no HTTP request ever blocks on
# SMTP. Set SMTP_BLOCKING=1 to send inline instead (used by the tests).
_SEND_BLOCKING = os.environ.get("SMTP_BLOCKING", "").strip() in ("1", "true", "True")


def _log(msg: str):
    """
    Print without ever raising. The Windows console is cp1252, so a stray
    non-ASCII character in a log line raises UnicodeEncodeError — which, inside
    send_email's try block, used to be caught and reported as a send failure
    even though the mail had already gone out.
    """
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def _cfg():
    return {
        "host":      os.environ.get("SMTP_HOST",      "smtp.gmail.com"),
        "port":      int(os.environ.get("SMTP_PORT",  587)),
        "user":      os.environ.get("SMTP_USER",      ""),
        "password":  os.environ.get("SMTP_PASSWORD",  ""),
        "from_name": os.environ.get("EMAIL_FROM_NAME", "FabricFlow International"),
        "default_admin_email": os.environ.get("DEFAULT_ADMIN_EMAIL", "")
    }

def _wrap_html(title: str, content: str) -> str:
    """Wraps email content in a premium black, white, and gray gradient HTML layout."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f8f9fa; margin: 0; padding: 0; }}
            .container {{ max-width: 600px; margin: 40px auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }}
            .header {{ background: linear-gradient(135deg, #111827 0%, #374151 100%); padding: 30px 40px; text-align: center; }}
            .header h1 {{ color: #ffffff; margin: 0; font-size: 24px; font-weight: 600; letter-spacing: 0.5px; }}
            .content {{ padding: 40px; color: #374151; line-height: 1.6; font-size: 15px; }}
            .content h2 {{ color: #111827; margin-top: 0; font-size: 20px; }}
            .footer {{ background-color: #000000; padding: 25px 40px; text-align: center; color: #9ca3af; font-size: 13px; }}
            .footer p {{ margin: 5px 0; }}
            ul {{ padding-left: 20px; }}
            li {{ margin-bottom: 8px; }}
            strong {{ color: #111827; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{title}</h1>
            </div>
            <div class="content">
                {content}
            </div>
            <div class="footer">
                <p>&copy; 2026 FabricFlow International. All rights reserved.</p>
                <p>This is an automated notification. Please do not reply.</p>
            </div>
        </div>
    </body>
    </html>
    """


def send_email(to: str, subject: str, html_body: str, cc: str = None) -> bool:
    """
    Queue a single HTML email for delivery via Gmail SMTP.
    Automatically CCs the DEFAULT_ADMIN_EMAIL unless it's already the recipient.

    By default this hands the send to a background thread and returns True
    immediately, so a slow mail server can never stall the HTTP request that
    triggered it. Set SMTP_BLOCKING=1 to send inline and get a real
    success/failure boolean back.
    """
    cfg = _cfg()
    if not cfg["user"] or not cfg["password"]:
        _log(f"[email] SMTP not configured - would have sent to {to}: {subject}")
        return False

    if _SEND_BLOCKING:
        return _send_email_sync(to, subject, html_body, cc)

    threading.Thread(
        target=_send_email_sync,
        args=(to, subject, html_body, cc),
        daemon=True,
    ).start()
    return True


def _send_email_sync(to: str, subject: str, html_body: str, cc: str = None) -> bool:
    """Actually open the SMTP connection and deliver. Never raises."""
    cfg = _cfg()
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f'{cfg["from_name"]} <{cfg["user"]}>'
        msg["To"]      = to
        
        # Build CC list
        cc_list = []
        if cc:
            cc_list.append(cc)
        
        default_admin = cfg["default_admin_email"]
        if default_admin and default_admin != to and default_admin not in cc_list:
            cc_list.append(default_admin)
            
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)

        rcpt = [to] + cc_list

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=SMTP_TIMEOUT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(cfg["user"], cfg["password"])
            smtp.sendmail(cfg["user"], rcpt, msg.as_string())
    except Exception as exc:
        _log(f"[email] ERROR sending to {to}: {exc}")
        return False

    # Logging lives outside the try so a console-encoding error can never be
    # mistaken for a delivery failure.
    _log(f"[email] Sent -> {to} (CC: {', '.join(cc_list)}) | {subject}")
    return True


# ── Email Templates ────────────────────────────────────────────────────────

def send_style_approved(buyer_email: str, style_number: str):
    content = f"""<h2>Your style was approved</h2>
    <p>Good news — your submitted style <strong>{style_number}</strong> has been reviewed and
    <strong>approved</strong>.</p>
    <p>It is now available in the catalog, so you can select it when placing sample or bulk orders.</p>"""
    html = _wrap_html("Style Approved", content)
    send_email(buyer_email, f"Style Approved — {style_number}", html)


def send_style_rejected(buyer_email: str, style_number: str, reason: str = None):
    reason_html = f"<p><strong>Reason:</strong> {reason}</p>" if reason else ""
    content = f"""<h2>Your style was not approved</h2>
    <p>Your submitted style <strong>{style_number}</strong> was reviewed and could not be approved
    at this time.</p>
    {reason_html}
    <p>You are welcome to submit an updated version with the required details.</p>"""
    html = _wrap_html("Style Rejected", content)
    send_email(buyer_email, f"Style Update — {style_number}", html)


def send_buyer_registered(admin_email: str, company_name: str):
    content = f"""<h2>Action Required: New Buyer</h2>
    <p>A new buyer, <strong>{company_name}</strong>, has registered on the platform and is currently awaiting approval.</p>
    <p>Please log in to the admin dashboard to review their details and approve their account to allow them to place orders.</p>"""
    html = _wrap_html("Registration Pending Approval", content)
    send_email(admin_email, f"New Registration: {company_name}", html)


def send_buyer_registration_received(buyer_email: str, company_name: str):
    content = f"""<h2>Registration Received</h2>
    <p>Dear {company_name},</p>
    <p>Thank you for registering with FabricFlow International.</p>
    <p>Your account is currently under review by our administration team. You will receive another email as soon as your account has been approved, at which point you will be able to log in and submit production orders.</p>"""
    html = _wrap_html("Welcome to FabricFlow", content)
    send_email(buyer_email, "Registration Received - FabricFlow", html)


def send_buyer_approved(buyer_email: str, buyer_name: str):
    content = f"""<h2>Account Approved!</h2>
    <p>Dear {buyer_name},</p>
    <p>Great news! Your account has been fully approved by our team.</p>
    <p>You can now log in to the FabricFlow portal to submit new sample requests and bulk production orders.</p>"""
    html = _wrap_html("Account Approved", content)
    send_email(buyer_email, "Your Account is Approved - FabricFlow", html)


def send_buyer_rejected(buyer_email: str, buyer_name: str):
    content = f"""<h2>Account Registration Update</h2>
    <p>Dear {buyer_name},</p>
    <p>Unfortunately, your registration could not be approved at this time.</p>
    <p>If you believe this is an error, please contact our support team.</p>"""
    html = _wrap_html("Registration Update", content)
    send_email(buyer_email, "Registration Update - FabricFlow", html)


def send_new_sample_order_to_admin(admin_email: str, buyer_name: str, buyer_email: str, style_number: str, order_id: int):
    content = f"""<h2>New Sample Order Received</h2>
    <p>A new sample order has been submitted and requires your review.</p>
    <ul>
        <li><strong>Order ID:</strong> {order_id}</li>
        <li><strong>Style Number:</strong> {style_number}</li>
        <li><strong>Buyer:</strong> {buyer_name}</li>
    </ul>
    <p>Please log in to the admin portal to review the C1 feasibility result and assign a plant.</p>"""
    html = _wrap_html("New Sample Order", content)
    send_email(admin_email, f"New Sample Order — {style_number}", html, cc=buyer_email)


def send_sample_order_assigned_to_plant(plant_email: str, plant_name: str, style_number: str, sample_qty: int, order_id: int):
    content = f"""<h2>Sample Order Assignment</h2>
    <p>A new sample order has been assigned to your plant.</p>
    <ul>
        <li><strong>Order ID:</strong> {order_id}</li>
        <li><strong>Style Number:</strong> {style_number}</li>
        <li><strong>Sample Qty:</strong> {sample_qty}</li>
    </ul>
    <p>Please log in to the plant portal to view the full details and mark it ready when complete.</p>"""
    html = _wrap_html(f"Assigned to {plant_name}", content)
    send_email(plant_email, f"New Sample Order Assigned — {style_number}", html)


def send_new_bulk_order_to_admin(admin_email: str, buyer_name: str, buyer_email: str, style_number: str, order_id: int, qty: int):
    content = f"""<h2>New Bulk Order Received</h2>
    <p>A bulk order is awaiting your review and plant assignment.</p>
    <ul>
        <li><strong>Order ID:</strong> {order_id}</li>
        <li><strong>Style Number:</strong> {style_number}</li>
        <li><strong>Buyer:</strong> {buyer_name}</li>
        <li><strong>Quantity:</strong> {qty:,}</li>
    </ul>
    <p>Please review the C2 analysis and assign plant(s).</p>"""
    html = _wrap_html("New Bulk Order", content)
    send_email(admin_email, f"New Bulk Order — {style_number}", html, cc=buyer_email)


def send_bulk_order_assigned_to_plant(plant_email: str, plant_name: str, style_number: str, qty: int, order_id: int):
    content = f"""<h2>Bulk Order Assignment</h2>
    <p>A bulk order has been assigned to your plant for production.</p>
    <ul>
        <li><strong>Order ID:</strong> {order_id}</li>
        <li><strong>Style Number:</strong> {style_number}</li>
        <li><strong>Quantity:</strong> {qty:,}</li>
    </ul>
    <p>Log in to the plant portal to view the full production schedule and start submitting daily logs.</p>"""
    html = _wrap_html(f"Assigned to {plant_name}", content)
    send_email(plant_email, f"Bulk Order Assigned — {style_number}", html)


def send_order_approved_to_buyer(buyer_email: str, buyer_name: str, style_number: str, order_id: int):
    content = f"""<h2>Order Approved & Assigned</h2>
    <p>Dear {buyer_name},</p>
    <p>Your order for style <strong>{style_number}</strong> (Order #{order_id}) has been successfully approved by the admin and assigned to a production plant.</p>
    <p>You can track its progress in your dashboard.</p>"""
    html = _wrap_html("Order In Production", content)
    send_email(buyer_email, f"Order Approved — {style_number}", html)


def send_critical_risk_alert(admin_email: str, plant_email: str, plant_name: str, style_number: str, order_id: int, risk_type: str, recommendation: str):
    content = f"""<h2 style="color:#dc2626;">⚠️ Critical Production Risk Detected</h2>
    <p>A critical risk has been flagged by AI Component 3 for the following order:</p>
    <ul>
        <li><strong>Order ID:</strong> {order_id}</li>
        <li><strong>Style Number:</strong> {style_number}</li>
        <li><strong>Plant:</strong> {plant_name}</li>
        <li><strong>Risk Type:</strong> {risk_type}</li>
        <li><strong>Recommended Action:</strong> {recommendation}</li>
    </ul>
    <p>Immediate attention is required to prevent shipment delays. Please log in to the portal for details.</p>"""
    html = _wrap_html("Critical Risk Alert", content)
    send_email(admin_email, f"⚠️ CRITICAL RISK — Order {order_id}", html, cc=plant_email)


def send_order_ready_to_buyer(buyer_email: str, buyer_name: str, style_number: str, order_id: int, plant_name: str):
    content = f"""<h2>Order Ready for Shipment 🎉</h2>
    <p>Dear {buyer_name},</p>
    <p>Excellent news! Your order is ready and waiting for shipment.</p>
    <ul>
        <li><strong>Order ID:</strong> {order_id}</li>
        <li><strong>Style Number:</strong> {style_number}</li>
        <li><strong>Completed by:</strong> {plant_name}</li>
    </ul>
    <p>The shipment will be confirmed by our team shortly.</p>"""
    html = _wrap_html("Order Ready", content)
    send_email(buyer_email, f"Your Order Is Ready — {style_number}", html)


def send_order_ready_to_admin(admin_email: str, plant_name: str, style_number: str, order_id: int):
    content = f"""<h2>Order Ready — Confirm Shipment</h2>
    <p><strong>{plant_name}</strong> has marked the following order as 100% complete and ready.</p>
    <ul>
        <li><strong>Order ID:</strong> {order_id}</li>
        <li><strong>Style Number:</strong> {style_number}</li>
    </ul>
    <p>Please log in to the admin portal to confirm shipment.</p>"""
    html = _wrap_html("Production Complete", content)
    send_email(admin_email, f"Plant Marked Order Ready — {style_number}", html)


def send_order_shipped_to_buyer(buyer_email: str, buyer_name: str, style_number: str, order_id: int):
    content = f"""<h2>Your Order Has Been Shipped 🚚</h2>
    <p>Dear {buyer_name},</p>
    <p>Order <strong>#{order_id}</strong> (Style: {style_number}) has been confirmed as shipped by our logistics team.</p>
    <p>Thank you for doing business with FabricFlow International!</p>"""
    html = _wrap_html("Order Shipped", content)
    send_email(buyer_email, f"Order Shipped — {style_number}", html)
