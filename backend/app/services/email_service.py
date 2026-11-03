import os
import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Tuple
from backend.app.core.config import settings

logger = logging.getLogger("borrowhub.email")


def send_email_otp(
    to_email: str,
    recipient_name: str,
    otp: str,
    purpose: str = "VERIFICATION"
) -> Tuple[bool, str]:
    """
    Send a 6-digit OTP code to a student's SVNIT email address.
    If SMTP credentials are provided in .env (e.g. Gmail App Password),
    sends a real email. Otherwise logs clearly to terminal and saves debug state.
    """
    clean_email = to_email.strip().lower()
    clean_name = recipient_name.strip() if recipient_name else "Student"

    if purpose == "PASSWORD_RESET":
        subject = f"BorrowHub Password Reset Code: {otp}"
        action_text = "reset your BorrowHub account password"
    else:
        subject = f"Your BorrowHub Verification Code: {otp}"
        action_text = "verify your official SVNIT student account"

    # Plain text version
    text_content = f"""Hello {clean_name},

Your BorrowHub verification code is: {otp}

Use this 6-digit code to {action_text}.
This code will expire in {settings.OTP_EXPIRY_MINUTES} minutes.

If you did not request this code, please ignore this email.

Best regards,
BorrowHub Team
SVNIT Surat Campus Community
"""

    # Responsive HTML version
    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f8f6ef; margin: 0; padding: 20px; }}
    .container {{ max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 14px; overflow: hidden; border: 1px solid #e5e0d3; box-shadow: 0 4px 18px rgba(0,0,0,0.06); }}
    .header {{ background: #8b2b1d; color: #ffffff; padding: 24px 28px; text-align: center; }}
    .header h1 {{ margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }}
    .header p {{ margin: 4px 0 0; font-size: 13px; opacity: 0.9; }}
    .body {{ padding: 30px 28px; color: #2d3748; line-height: 1.6; font-size: 15px; }}
    .otp-box {{ background: #fdfaf3; border: 2px dashed #8b2b1d; border-radius: 12px; padding: 18px; text-align: center; margin: 24px 0; }}
    .otp-code {{ font-size: 34px; font-weight: 800; letter-spacing: 8px; color: #8b2b1d; font-family: monospace; }}
    .expiry {{ font-size: 12px; color: #718096; margin-top: 6px; }}
    .footer {{ background: #f8f6ef; padding: 18px 28px; font-size: 12px; color: #a0aec0; text-align: center; border-top: 1px solid #e5e0d3; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>BorrowHub</h1>
      <p>SVNIT Surat Campus Resource Sharing Platform</p>
    </div>
    <div class="body">
      <p>Hello <strong>{clean_name}</strong>,</p>
      <p>Thank you for joining BorrowHub. Please use the verification code below to {action_text}:</p>
      <div class="otp-box">
        <div class="otp-code">{otp}</div>
        <div class="expiry">Valid for {settings.OTP_EXPIRY_MINUTES} minutes</div>
      </div>
      <p style="font-size: 13px; color: #718096;">
        Security Notice: BorrowHub administrators will never ask for your verification code or password.
      </p>
    </div>
    <div class="footer">
      Sardar Vallabhbhai National Institute of Technology (SVNIT), Surat<br>
      Share &bull; Borrow &bull; Grow
    </div>
  </div>
</body>
</html>"""

    # If SMTP is configured, attempt real email delivery
    if settings.SMTP_USER and settings.SMTP_PASSWORD:
        try:
            sender_email = settings.SMTP_USER.strip() if settings.SMTP_USER else settings.SMTP_FROM_EMAIL.strip()
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{settings.SMTP_FROM_NAME} <{sender_email}>"
            msg["To"] = clean_email

            msg.attach(MIMEText(text_content, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            port = int(settings.SMTP_PORT)
            if port == 465:
                server = smtplib.SMTP_SSL(settings.SMTP_HOST, port, timeout=15)
            else:
                server = smtplib.SMTP(settings.SMTP_HOST, port, timeout=15)
                server.ehlo()
                if settings.SMTP_TLS:
                    server.starttls()
                    server.ehlo()

            server.login(settings.SMTP_USER.strip(), settings.SMTP_PASSWORD.strip())
            server.sendmail(sender_email, [clean_email], msg.as_string())
            server.quit()

            print(f"[REAL EMAIL SENT] OTP verification code delivered to {clean_email} via {settings.SMTP_HOST}")
            return True, f"Verification email successfully delivered to {clean_email}."
        except Exception as e:
            logger.error(f"SMTP email dispatch failed: {e}")
            print(f"[SMTP ERROR] Failed to send email via {settings.SMTP_HOST}: {e}")

    # Fallback / Simulated output for local development or when credentials are not yet set
    print("=" * 80)
    print(f"[BORROWHUB EMAIL DISPATCH] (Simulated / Local Dev Mode)")
    print(f"To:        {clean_email} ({clean_name})")
    print(f"Subject:   {subject}")
    print(f"OTP Code:  {otp}")
    print(f"Expires:   {settings.OTP_EXPIRY_MINUTES} minutes")
    print(f"Notice:    Set SMTP_USER and SMTP_PASSWORD in backend/.env to deliver live emails.")
    print("=" * 80)

    # Save debug record so UI or test runners can read the latest code
    try:
        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
        os.makedirs(out_dir, exist_ok=True)
        rec_path = os.path.join(out_dir, "latest_sent_otp.json")
        with open(rec_path, "w", encoding="utf-8") as f:
            json.dump({
                "to_email": clean_email,
                "name": clean_name,
                "otp": otp,
                "purpose": purpose
            }, f)
    except Exception:
        pass

    return False, f"OTP generated: {otp} (Configure SMTP in backend/.env for real email delivery)"


def send_dispute_alert_email(
    admin_email: str,
    admin_name: str,
    dispute_id: int,
    loan_id: int,
    dispute_type: str,
    claimed_amount: float,
    description: str,
    raised_by_name: str,
    evidence_urls: list
) -> Tuple[bool, str]:
    """
    Send an email notification to campus administrators whenever a damage claim or
    dispute is filed, including attached photo evidence links.
    """
    clean_email = admin_email.strip().lower()
    clean_name = admin_name.strip() if admin_name else "Campus Administrator"
    subject = f"⚠️ [BorrowHub Dispute Alert] New Damage Claim #{dispute_id} (Loan #{loan_id})"

    evidence_text = "\n".join([f"- {url}" for url in evidence_urls]) if evidence_urls else "No photo attachments provided."
    evidence_html = "".join([f'<a href="{url}" target="_blank" style="display:inline-block; margin:4px;"><img src="{url}" style="width:90px; height:90px; object-fit:cover; border-radius:6px; border:1px solid #ccc;"></a>' for url in evidence_urls]) if evidence_urls else '<p style="color:#718096; font-size:13px;">No photo proof attached.</p>'

    text_content = f"""BorrowHub Campus Manager Alert

A new damage claim or dispute has been filed and requires administrative mediation:

Dispute ID:      #{dispute_id}
Loan ID:         #{loan_id}
Dispute Type:    {dispute_type}
Filed By:        {raised_by_name}
Claimed Amount:  ₹{claimed_amount:.2f}
Description:
{description}

Attached Photo Proof:
{evidence_text}

Please log in to the BorrowHub Admin Dashboard to review evidence and mediate deposit settlement:
http://127.0.0.1:8000
"""

    html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:'Segoe UI',sans-serif; background:#f8f6ef; padding:20px; margin:0;">
  <div style="max-width:560px; margin:0 auto; background:#ffffff; border-radius:12px; border:1px solid #e5e0d3; overflow:hidden;">
    <div style="background:#8b2b1d; color:#ffffff; padding:20px 24px;">
      <h2 style="margin:0; font-size:20px;">🛡️ BorrowHub Dispute & Damage Claim</h2>
      <p style="margin:4px 0 0; font-size:13px; opacity:0.9;">Action required by Campus Administration</p>
    </div>
    <div style="padding:24px; color:#2d3748; font-size:14px; line-height:1.6;">
      <p>Hello <strong>{clean_name}</strong>,</p>
      <p>A student has reported an issue requiring deposit mediation:</p>
      <div style="background:#fef2f2; border-left:4px solid #b91c1c; padding:12px 16px; margin:14px 0; border-radius:4px;">
        <p style="margin:2px 0;"><strong>Dispute:</strong> #{dispute_id} (Loan #{loan_id})</p>
        <p style="margin:2px 0;"><strong>Type:</strong> {dispute_type}</p>
        <p style="margin:2px 0;"><strong>Filed by:</strong> {raised_by_name}</p>
        <p style="margin:2px 0;"><strong>Claimed Amount:</strong> <span style="color:#b91c1c; font-weight:700;">₹{claimed_amount:.2f}</span></p>
      </div>
      <p><strong>Description of Damage / Issue:</strong></p>
      <blockquote style="background:#f9fafb; border:1px solid #e5e7eb; padding:12px; border-radius:6px; margin:8px 0; font-style:italic;">
        "{description}"
      </blockquote>
      <p style="margin-top:16px;"><strong>Attached Photo Proof of Damage:</strong></p>
      <div style="margin:8px 0;">{evidence_html}</div>
      <div style="text-align:center; margin-top:24px;">
        <a href="http://127.0.0.1:8000" style="background:#8b2b1d; color:#ffffff; text-decoration:none; padding:10px 20px; border-radius:8px; font-weight:600; display:inline-block;">Open Admin Mediation Panel →</a>
      </div>
    </div>
  </div>
</body>
</html>"""

    if settings.SMTP_USER and settings.SMTP_PASSWORD:
        try:
            sender_email = settings.SMTP_USER.strip() if settings.SMTP_USER else settings.SMTP_FROM_EMAIL.strip()
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{settings.SMTP_FROM_NAME} <{sender_email}>"
            msg["To"] = clean_email
            msg.attach(MIMEText(text_content, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            port = int(settings.SMTP_PORT)
            if port == 465:
                server = smtplib.SMTP_SSL(settings.SMTP_HOST, port, timeout=15)
            else:
                server = smtplib.SMTP(settings.SMTP_HOST, port, timeout=15)
                server.ehlo()
                if settings.SMTP_TLS:
                    server.starttls()
                    server.ehlo()

            server.login(settings.SMTP_USER.strip(), settings.SMTP_PASSWORD.strip())
            server.sendmail(sender_email, [clean_email], msg.as_string())
            server.quit()
            print(f"[REAL EMAIL SENT] Dispute alert sent to admin {clean_email}")
            return True, f"Admin email alert sent to {clean_email}."
        except Exception as e:
            logger.error(f"Failed to email dispute alert: {e}")
            print(f"[SMTP ERROR] Failed to email dispute alert to {clean_email}: {e}")

    print("=" * 80)
    print(f"[BORROWHUB ADMIN DISPUTE ALERT] (Local Dev / Terminal Mode)")
    print(f"To:             {clean_email} ({clean_name})")
    print(f"Subject:        {subject}")
    print(f"Dispute ID:     #{dispute_id}")
    print(f"Claimed:        ₹{claimed_amount:.2f}")
    print(f"Evidence Photos:{len(evidence_urls)}")
    print("=" * 80)
    return False, f"Dispute alert recorded for admin {clean_email}."
