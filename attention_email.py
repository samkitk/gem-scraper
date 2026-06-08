"""
'Draw Attention' email — sends a single tender to EMAIL_TO with Yes/No decision buttons.
Separate from the daily digest (email_digest.py); triggered manually from the dashboard.
"""
import logging
import html as html_lib

import resend

import config

logger = logging.getLogger("gem-attention")

resend.api_key = config.RESEND_API_KEY
EMAIL_TO = config.EMAIL_TO
EMAIL_FROM = config.EMAIL_FROM
DASHBOARD_URL = config.DASHBOARD_URL.rstrip("/")

# Brand
RED = "#ef3e46"
RED_DARK = "#c4161f"
GREEN = "#22c55e"


def _clean(value, fallback="—"):
    """Stringify a DB value, treating None/'None'/'null' as empty."""
    if value is None:
        return fallback
    s = str(value).strip()
    if s == "" or s.lower() in ("none", "null"):
        return fallback
    return s


def build_attention_html(tender: dict) -> str:
    """Build the single-tender 'Draw Attention' email body."""
    bid = tender["bid_number"]
    folder = bid.replace("/", "-")
    tender_url = f"{DASHBOARD_URL}/tender/{folder}"
    yes_url = f"{tender_url}/mark/applied"
    no_url = f"{tender_url}/mark/not_applying"

    dept = html_lib.escape(_clean(tender.get("department")))
    location = html_lib.escape(_clean(tender.get("location"), "Not specified"))
    value = html_lib.escape(_clean(tender.get("estimated_value"), "Not specified"))
    end_date = html_lib.escape(_clean(tender.get("end_date")))
    scope = html_lib.escape(_clean(tender.get("scope_of_work"), "")[:400])
    bid_safe = html_lib.escape(bid)

    scope_block = (
        f'<tr><td style="padding:6px 0;color:#888;font-size:12px;text-transform:uppercase;'
        f'letter-spacing:0.04em;vertical-align:top;width:120px;">Scope</td>'
        f'<td style="padding:6px 0;color:#444;font-size:13px;">{scope}</td></tr>'
        if scope else ""
    )

    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <div style="max-width:620px;margin:20px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
        <div style="background:linear-gradient(135deg,{RED},{RED_DARK});padding:24px 28px;color:#fff;">
            <p style="margin:0 0 4px;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;opacity:0.85;">📣 Drawing your attention</p>
            <h1 style="margin:0;font-size:18px;font-weight:700;font-family:monospace;">{bid_safe}</h1>
        </div>

        <div style="padding:24px 28px;">
            <p style="margin:0 0 18px;font-size:14px;color:#333;">We'd like to draw your attention to this tender. Are we applying?</p>

            <table style="width:100%;border-collapse:collapse;margin:0 0 22px;">
                <tr><td style="padding:6px 0;color:#888;font-size:12px;text-transform:uppercase;letter-spacing:0.04em;width:120px;">Department</td>
                    <td style="padding:6px 0;color:#444;font-size:13px;font-weight:500;">{dept}</td></tr>
                <tr><td style="padding:6px 0;color:#888;font-size:12px;text-transform:uppercase;letter-spacing:0.04em;">Location</td>
                    <td style="padding:6px 0;color:#444;font-size:13px;">{location}</td></tr>
                <tr><td style="padding:6px 0;color:#888;font-size:12px;text-transform:uppercase;letter-spacing:0.04em;">Est. Value</td>
                    <td style="padding:6px 0;color:{GREEN};font-size:13px;font-family:monospace;font-weight:600;">{value}</td></tr>
                <tr><td style="padding:6px 0;color:#888;font-size:12px;text-transform:uppercase;letter-spacing:0.04em;">End Date</td>
                    <td style="padding:6px 0;color:#444;font-size:13px;">{end_date}</td></tr>
                {scope_block}
            </table>

            <!-- Yes / No decision buttons -->
            <table style="width:100%;border-collapse:separate;border-spacing:8px 0;">
                <tr>
                    <td style="width:50%;">
                        <a href="{yes_url}" style="display:block;text-align:center;padding:13px 0;background:{GREEN};color:#fff;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;">✅ Yes, applied</a>
                    </td>
                    <td style="width:50%;">
                        <a href="{no_url}" style="display:block;text-align:center;padding:13px 0;background:{RED};color:#fff;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;">❌ Not applying</a>
                    </td>
                </tr>
            </table>

            <p style="margin:18px 0 0;text-align:center;">
                <a href="{tender_url}" style="color:{RED};font-size:13px;text-decoration:none;font-weight:600;">Open full tender on dashboard →</a>
            </p>
        </div>

        <div style="padding:16px 28px;text-align:center;border-top:1px solid #eee;">
            <p style="margin:0;font-size:11px;color:#bbb;">GeM Scraper · You'll be asked to sign in before your choice is saved.</p>
        </div>
    </div>
</body>
</html>"""


def send_attention_email(tender: dict) -> tuple[bool, str]:
    """Send the Draw Attention email for one tender. Returns (success, message)."""
    if not resend.api_key:
        return False, "RESEND_API_KEY not set"
    if not EMAIL_TO:
        return False, "EMAIL_TO not set"

    bid = tender.get("bid_number", "?")
    html = build_attention_html(tender)
    subject = f"📣 Draw attention: {bid} — {_clean(tender.get('department'), '')[:40]}".strip(" —")

    try:
        result = resend.Emails.send({
            "from": EMAIL_FROM,
            "to": [EMAIL_TO],
            "subject": subject,
            "html": html,
        })
        logger.info(f"📣 Attention email sent for {bid} to {EMAIL_TO} ({result.get('id', '?')})")
        return True, "sent"
    except Exception as e:
        logger.error(f"Failed to send attention email for {bid}: {e}")
        return False, str(e)
