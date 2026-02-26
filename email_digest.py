"""
Daily Email Digest for GeM Tender Updates.
Sends only NEW tenders since the last email, with Gujarat tenders grouped first.
"""
import logging
from datetime import datetime

import resend

import config
import db

logger = logging.getLogger("gem-email")

resend.api_key = config.RESEND_API_KEY
EMAIL_TO = config.EMAIL_TO
EMAIL_FROM = config.EMAIL_FROM
DASHBOARD_URL = config.DASHBOARD_URL

# Gujarat cities/regions for priority grouping
GUJARAT_KEYWORDS = [
    "gujarat", "ahmedabad", "gandhinagar", "vadodara", "baroda", "surat",
    "rajkot", "bhavnagar", "jamnagar", "bharuch", "anand", "ankleshwar",
    "halol", "nadiad", "valsad", "mehsana", "morbi", "junagadh",
    "porbandar", "kutch", "gandhidham", "navsari", "vapi", "dahod",
    "godhra", "palanpur", "surendranagar", "amreli", "botad",
]


def get_last_email_time() -> str | None:
    """Get the timestamp of the last sent email."""
    conn = db.get_connection()
    row = conn.execute(
        "SELECT sent_at FROM email_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row["sent_at"] if row else None


def log_email_sent(tender_count: int):
    """Record that an email was sent."""
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO email_log (sent_at, tender_count) VALUES (?, ?)",
        (datetime.now().isoformat(), tender_count),
    )
    conn.commit()
    conn.close()


def get_new_tenders() -> list[dict]:
    """Get tenders scraped since the last email was sent."""
    last_sent = get_last_email_time()

    conn = db.get_connection()
    if last_sent:
        rows = conn.execute(
            "SELECT * FROM tenders WHERE scraped_at > ? ORDER BY scraped_at DESC",
            (last_sent,),
        ).fetchall()
    else:
        # First email ever — send all processed tenders
        rows = conn.execute(
            "SELECT * FROM tenders WHERE processed = 1 ORDER BY scraped_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def is_gujarat(location: str) -> bool:
    """Check if a location string matches Gujarat region."""
    if not location:
        return False
    loc_lower = location.lower()
    return any(kw in loc_lower for kw in GUJARAT_KEYWORDS)


def build_tender_rows(tenders: list[dict]) -> str:
    """Build HTML table rows for a list of tenders."""
    if not tenders:
        return '<tr><td colspan="5" style="padding:20px;text-align:center;color:#999;font-size:13px;">No tenders in this category</td></tr>'

    rows = ""
    for t in tenders:
        bid = t["bid_number"]
        dept = (t.get("department") or "—")[:50]
        loc = t.get("location") or "—"
        value = t.get("estimated_value") or "—"
        end = t.get("end_date") or "—"
        scope = (t.get("scope_of_work") or "—")[:140]
        folder = bid.replace("/", "-")
        link = f"{DASHBOARD_URL}/tender/{folder}"

        rows += f"""
        <tr>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;">
                <a href="{link}" style="color:#6c63ff;font-weight:600;font-family:monospace;font-size:12px;text-decoration:none;">{bid}</a>
            </td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;font-size:12px;color:#555;">{dept}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;font-size:12px;color:#555;font-weight:500;">{loc}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;font-size:12px;color:#22c55e;font-family:monospace;">{value}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;font-size:11px;color:#888;">{end}</td>
        </tr>
        <tr>
            <td colspan="5" style="padding:3px 12px 8px;border-bottom:1px solid #ddd;font-size:11px;color:#888;">{scope}</td>
        </tr>"""
    return rows


def build_section(title: str, emoji: str, color: str, count: int, tenders: list[dict]) -> str:
    """Build a section header + table for a group of tenders."""
    rows = build_tender_rows(tenders)
    return f"""
    <div style="margin:0 0 24px;">
        <div style="padding:12px 16px;background:{color};border-radius:8px 8px 0 0;display:flex;align-items:center;justify-content:space-between;">
            <span style="font-weight:700;font-size:14px;color:#333;">{emoji} {title}</span>
            <span style="background:#fff;color:{color.replace('0.08','1').replace('rgba','rgb')};padding:3px 10px;border-radius:100px;font-size:11px;font-weight:700;">{count}</span>
        </div>
        <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #eee;border-top:none;border-radius:0 0 8px 8px;">
            <thead>
                <tr style="background:#fafafa;">
                    <th style="padding:8px 12px;text-align:left;font-size:10px;color:#999;text-transform:uppercase;font-weight:600;">Bid</th>
                    <th style="padding:8px 12px;text-align:left;font-size:10px;color:#999;text-transform:uppercase;font-weight:600;">Department</th>
                    <th style="padding:8px 12px;text-align:left;font-size:10px;color:#999;text-transform:uppercase;font-weight:600;">Location</th>
                    <th style="padding:8px 12px;text-align:left;font-size:10px;color:#999;text-transform:uppercase;font-weight:600;">Value</th>
                    <th style="padding:8px 12px;text-align:left;font-size:10px;color:#999;text-transform:uppercase;font-weight:600;">End Date</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>"""


def build_email_html(gujarat_tenders: list[dict], other_tenders: list[dict], stats: dict) -> str:
    """Build the full HTML email with Gujarat priority section."""
    now = datetime.now().strftime("%d %b %Y, %I:%M %p")
    total_new = len(gujarat_tenders) + len(other_tenders)

    gujarat_section = build_section(
        "Gujarat Region", "🏠", "rgba(34,197,94,0.08)",
        len(gujarat_tenders), gujarat_tenders
    )
    other_section = build_section(
        "Other Regions", "🌍", "rgba(59,130,246,0.08)",
        len(other_tenders), other_tenders
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
        <div style="max-width:720px;margin:20px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
            <!-- Header -->
            <div style="background:linear-gradient(135deg,#6c63ff,#a78bfa);padding:24px 28px;color:#fff;">
                <h1 style="margin:0;font-size:20px;font-weight:700;">💎 GeM Tender Digest</h1>
                <p style="margin:6px 0 0;font-size:13px;opacity:0.85;">{now}</p>
                <p style="margin:4px 0 0;font-size:15px;font-weight:600;">{total_new} new tender{"s" if total_new != 1 else ""} found</p>
            </div>

            <!-- Stats Bar -->
            <table style="width:100%;border-collapse:collapse;background:#fafafa;border-bottom:1px solid #eee;">
                <tr>
                    <td style="padding:14px;text-align:center;width:25%;">
                        <div style="font-size:20px;font-weight:700;color:#6c63ff;">{stats['total_tenders']}</div>
                        <div style="font-size:10px;color:#999;text-transform:uppercase;">Total</div>
                    </td>
                    <td style="padding:14px;text-align:center;width:25%;">
                        <div style="font-size:20px;font-weight:700;color:#22c55e;">{len(gujarat_tenders)}</div>
                        <div style="font-size:10px;color:#999;text-transform:uppercase;">Gujarat (New)</div>
                    </td>
                    <td style="padding:14px;text-align:center;width:25%;">
                        <div style="font-size:20px;font-weight:700;color:#3b82f6;">{len(other_tenders)}</div>
                        <div style="font-size:10px;color:#999;text-transform:uppercase;">Others (New)</div>
                    </td>
                    <td style="padding:14px;text-align:center;width:25%;">
                        <div style="font-size:20px;font-weight:700;color:#f59e0b;">{stats['relevant_links']}</div>
                        <div style="font-size:10px;color:#999;text-transform:uppercase;">Rel. Links</div>
                    </td>
                </tr>
            </table>

            <!-- Tender Sections -->
            <div style="padding:20px 16px 0;">
                {gujarat_section}
                {other_section}
            </div>

            <!-- Footer -->
            <div style="padding:20px 28px;text-align:center;border-top:1px solid #eee;">
                <a href="{DASHBOARD_URL}" style="display:inline-block;padding:10px 24px;background:#6c63ff;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">Open Dashboard</a>
                <p style="margin:12px 0 0;font-size:11px;color:#bbb;">GeM Scraper · Event/Seminar/Workshop Tenders</p>
            </div>
        </div>
    </body>
    </html>"""


def send_digest() -> bool:
    """Send the email digest with only new tenders since last email. Returns True on success."""
    if not resend.api_key:
        logger.warning("RESEND_API_KEY not set, skipping email digest")
        return False
    if not EMAIL_TO:
        logger.warning("EMAIL_TO not set, skipping email digest")
        return False

    # Get only tenders scraped since last email
    new_tenders = get_new_tenders()

    if not new_tenders:
        logger.info("📭 No new tenders since last email — skipping digest")
        return True  # Not an error, just nothing new

    # Bifurcate: Gujarat first, then others
    gujarat = [t for t in new_tenders if is_gujarat(t.get("location", ""))]
    others = [t for t in new_tenders if not is_gujarat(t.get("location", ""))]

    stats = db.get_tender_stats()
    html = build_email_html(gujarat, others, stats)
    total = len(new_tenders)

    subject = f"💎 GeM: {total} new tender{'s' if total != 1 else ''}"
    if gujarat:
        subject += f" ({len(gujarat)} in Gujarat)"
    subject += f" · {datetime.now().strftime('%d %b')}"

    try:
        params = {
            "from": EMAIL_FROM,
            "to": [EMAIL_TO],
            "subject": subject,
            "html": html,
        }
        email = resend.Emails.send(params)
        logger.info(f"✉️  Digest sent to {EMAIL_TO}: {len(gujarat)} Gujarat + {len(others)} other ({email.get('id', '?')})")

        # Log this email so next time we only send newer tenders
        log_email_sent(total)
        return True
    except Exception as e:
        logger.error(f"Failed to send email digest: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format=config.LOG_FORMAT)
    send_digest()
