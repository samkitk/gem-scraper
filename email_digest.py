"""
Daily Email Digest for GeM Tender Updates.
Sends a summary of new/updated tenders via Resend.
"""
import os
import logging
from datetime import datetime, timedelta

import resend

import config
import db

logger = logging.getLogger("gem-email")

resend.api_key = config.RESEND_API_KEY
EMAIL_TO = config.EMAIL_TO
EMAIL_FROM = config.EMAIL_FROM
DASHBOARD_URL = config.DASHBOARD_URL


def get_recent_tenders(hours: int = 24) -> list[dict]:
    """Get tenders scraped in the last N hours."""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT * FROM tenders WHERE scraped_at >= ? ORDER BY scraped_at DESC",
        (cutoff,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def build_email_html(tenders: list[dict], stats: dict) -> str:
    """Build a clean HTML email digest."""
    now = datetime.now().strftime("%d %b %Y, %I:%M %p")

    rows_html = ""
    for t in tenders:
        bid = t["bid_number"]
        dept = t.get("department") or "—"
        loc = t.get("location") or "—"
        value = t.get("estimated_value") or "—"
        end = t.get("end_date") or "—"
        scope = (t.get("scope_of_work") or "—")[:120]
        folder = bid.replace("/", "-")
        link = f"{DASHBOARD_URL}/tender/{folder}"

        rows_html += f"""
        <tr>
            <td style="padding:10px 12px;border-bottom:1px solid #eee;">
                <a href="{link}" style="color:#6c63ff;font-weight:600;font-family:monospace;font-size:13px;">{bid}</a>
            </td>
            <td style="padding:10px 12px;border-bottom:1px solid #eee;font-size:13px;color:#555;max-width:200px;">{dept[:50]}</td>
            <td style="padding:10px 12px;border-bottom:1px solid #eee;font-size:13px;color:#555;">{loc}</td>
            <td style="padding:10px 12px;border-bottom:1px solid #eee;font-size:13px;color:#22c55e;font-family:monospace;">{value}</td>
            <td style="padding:10px 12px;border-bottom:1px solid #eee;font-size:12px;color:#888;">{end}</td>
        </tr>
        <tr>
            <td colspan="5" style="padding:4px 12px 10px;border-bottom:1px solid #ddd;font-size:12px;color:#777;">{scope}</td>
        </tr>"""

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
        <div style="max-width:700px;margin:20px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
            <!-- Header -->
            <div style="background:linear-gradient(135deg,#6c63ff,#a78bfa);padding:24px 28px;color:#fff;">
                <h1 style="margin:0;font-size:20px;font-weight:700;">💎 GeM Tender Digest</h1>
                <p style="margin:6px 0 0;font-size:13px;opacity:0.85;">{now} · {len(tenders)} new tenders</p>
            </div>

            <!-- Stats -->
            <div style="display:flex;padding:16px 28px;background:#fafafa;border-bottom:1px solid #eee;">
                <div style="flex:1;text-align:center;">
                    <div style="font-size:22px;font-weight:700;color:#6c63ff;">{stats['total_tenders']}</div>
                    <div style="font-size:11px;color:#999;text-transform:uppercase;">Total</div>
                </div>
                <div style="flex:1;text-align:center;">
                    <div style="font-size:22px;font-weight:700;color:#22c55e;">{stats['processed']}</div>
                    <div style="font-size:11px;color:#999;text-transform:uppercase;">Processed</div>
                </div>
                <div style="flex:1;text-align:center;">
                    <div style="font-size:22px;font-weight:700;color:#f59e0b;">{stats['relevant_links']}</div>
                    <div style="font-size:11px;color:#999;text-transform:uppercase;">Relevant Links</div>
                </div>
            </div>

            <!-- Table -->
            <div style="padding:0 12px;">
                <table style="width:100%;border-collapse:collapse;">
                    <thead>
                        <tr style="background:#fafafa;">
                            <th style="padding:10px 12px;text-align:left;font-size:11px;color:#999;text-transform:uppercase;font-weight:600;">Bid</th>
                            <th style="padding:10px 12px;text-align:left;font-size:11px;color:#999;text-transform:uppercase;font-weight:600;">Department</th>
                            <th style="padding:10px 12px;text-align:left;font-size:11px;color:#999;text-transform:uppercase;font-weight:600;">Location</th>
                            <th style="padding:10px 12px;text-align:left;font-size:11px;color:#999;text-transform:uppercase;font-weight:600;">Value</th>
                            <th style="padding:10px 12px;text-align:left;font-size:11px;color:#999;text-transform:uppercase;font-weight:600;">End Date</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html if rows_html else '<tr><td colspan="5" style="padding:24px;text-align:center;color:#999;">No new tenders in the last 24 hours</td></tr>'}
                    </tbody>
                </table>
            </div>

            <!-- Footer -->
            <div style="padding:20px 28px;text-align:center;border-top:1px solid #eee;">
                <a href="{DASHBOARD_URL}" style="display:inline-block;padding:10px 24px;background:#6c63ff;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">Open Dashboard</a>
                <p style="margin:12px 0 0;font-size:11px;color:#bbb;">GeM Scraper · Event/Seminar/Workshop Tenders</p>
            </div>
        </div>
    </body>
    </html>"""


def send_digest(hours: int = 24) -> bool:
    """Send the email digest. Returns True on success."""
    if not resend.api_key:
        logger.warning("RESEND_API_KEY not set, skipping email digest")
        return False
    if not EMAIL_TO:
        logger.warning("EMAIL_TO not set, skipping email digest")
        return False

    tenders = get_recent_tenders(hours)
    stats = db.get_tender_stats()
    html = build_email_html(tenders, stats)

    subject = f"💎 GeM Digest: {len(tenders)} tenders · {datetime.now().strftime('%d %b')}"

    try:
        params = {
            "from": EMAIL_FROM,
            "to": [EMAIL_TO],
            "subject": subject,
            "html": html,
        }
        email = resend.Emails.send(params)
        logger.info(f"✉️  Email digest sent to {EMAIL_TO} (id: {email.get('id', '?')})")
        return True
    except Exception as e:
        logger.error(f"Failed to send email digest: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format=config.LOG_FORMAT)
    send_digest()
