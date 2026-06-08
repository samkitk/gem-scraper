"""
Daily Email Digest for GeM Tender Updates.
Sends only NEW tenders since the last email, with Gujarat tenders grouped first.
"""
import logging
import html as html_lib
from datetime import datetime

import resend

import config
import db

logger = logging.getLogger("gem-email")

resend.api_key = config.RESEND_API_KEY
EMAIL_TO = config.EMAIL_TO
EMAIL_FROM = config.EMAIL_FROM
DASHBOARD_URL = config.DASHBOARD_URL.rstrip("/")

# ── Brand palette (light email, red accents) ──
RED = "#ef3e46"
RED_DARK = "#c4161f"
GREEN = "#16a34a"
AMBER = "#d97706"
BLUE = "#2563eb"


def _esc(value) -> str:
    """HTML-escape a value for safe embedding."""
    return html_lib.escape(str(value))


def _clean(value, fallback="—") -> str:
    """Stringify a DB value, treating None/'None'/'null'/empty as the fallback."""
    if value is None:
        return fallback
    s = str(value).strip()
    if s == "" or s.lower() in ("none", "null"):
        return fallback
    return s

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


def build_tender_card(tender: dict) -> str:
    """Build a single clean tender card for the digest email."""
    bid = tender["bid_number"]
    bid_safe = _esc(bid)
    dept = _esc(_clean(tender.get("department")))
    loc = _esc(_clean(tender.get("location"), "Location N/A"))
    value = _esc(_clean(tender.get("estimated_value"), ""))
    end = _esc(_clean(tender.get("end_date"), ""))
    scope = _esc(_clean(tender.get("scope_of_work"), "")[:160])
    folder = bid.replace("/", "-")
    link = f"{DASHBOARD_URL}/tender/{folder}"

    value_html = (
        f'<span style="font-family:monospace;font-size:13px;font-weight:700;color:{GREEN};white-space:nowrap;">{value}</span>'
        if value else ""
    )
    meta_bits = []
    if loc:
        meta_bits.append(f"📍 {loc}")
    if end:
        meta_bits.append(f"⏰ {end}")
    meta_line = "&nbsp;&nbsp;·&nbsp;&nbsp;".join(meta_bits)
    scope_html = (
        f'<div style="font-size:12px;color:#7a7f8a;margin-top:8px;line-height:1.55;">{scope}…</div>'
        if scope else ""
    )

    return f"""
    <table role="presentation" width="100%" style="border-collapse:separate;border-spacing:0;margin:0 0 10px;">
      <tr><td style="padding:14px 16px;background:#ffffff;border:1px solid #ececef;border-radius:10px;">
        <table role="presentation" width="100%" style="border-collapse:collapse;">
          <tr>
            <td style="vertical-align:top;">
              <a href="{link}" style="font-family:monospace;font-size:13px;font-weight:700;color:{RED};text-decoration:none;">{bid_safe}</a>
            </td>
            <td align="right" style="vertical-align:top;">{value_html}</td>
          </tr>
        </table>
        <div style="font-size:13px;color:#1a1a1f;font-weight:600;margin-top:7px;">{dept}</div>
        <div style="font-size:12px;color:#6b7280;margin-top:4px;">{meta_line}</div>
        {scope_html}
      </td></tr>
    </table>"""


def build_section(title: str, emoji: str, accent: str, count: int, tenders: list[dict]) -> str:
    """Build a section header + a stack of tender cards for a group of tenders."""
    if tenders:
        cards = "".join(build_tender_card(t) for t in tenders)
    else:
        cards = ('<div style="padding:18px;text-align:center;color:#aab;font-size:13px;'
                 'background:#fafafb;border:1px dashed #e5e5ea;border-radius:10px;">'
                 'Nothing new in this group</div>')

    return f"""
    <div style="margin:0 0 26px;">
        <table role="presentation" width="100%" style="border-collapse:collapse;margin:0 0 12px;">
          <tr>
            <td style="vertical-align:middle;">
              <span style="display:inline-block;width:4px;height:16px;background:{accent};border-radius:2px;vertical-align:middle;margin-right:9px;"></span>
              <span style="font-weight:700;font-size:14px;color:#1a1a1f;vertical-align:middle;">{emoji} {title}</span>
            </td>
            <td align="right" style="vertical-align:middle;">
              <span style="background:{accent};color:#fff;padding:2px 11px;border-radius:100px;font-size:11px;font-weight:700;">{count}</span>
            </td>
          </tr>
        </table>
        {cards}
    </div>"""


def build_email_html(gujarat_tenders: list[dict], other_tenders: list[dict], stats: dict) -> str:
    """Build the full HTML email with Gujarat priority section."""
    now = datetime.now().strftime("%d %b %Y, %I:%M %p")
    total_new = len(gujarat_tenders) + len(other_tenders)

    gujarat_section = build_section(
        "Gujarat Region", "🏠", GREEN,
        len(gujarat_tenders), gujarat_tenders
    )
    other_section = build_section(
        "Other Regions", "🌍", BLUE,
        len(other_tenders), other_tenders
    )

    plural = "s" if total_new != 1 else ""

    def stat_cell(value, label, color):
        return f"""
            <td style="padding:16px 8px;text-align:center;">
                <div style="font-size:22px;font-weight:800;color:{color};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">{value}</div>
                <div style="font-size:10px;color:#9aa0ab;text-transform:uppercase;letter-spacing:0.05em;margin-top:2px;">{label}</div>
            </td>"""

    return f"""\
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f1f1f4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
    <div style="max-width:640px;margin:0 auto;padding:24px 14px;">
        <div style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.07);">
            <!-- Header -->
            <div style="background:linear-gradient(135deg,{RED},{RED_DARK});padding:28px 28px 26px;color:#ffffff;">
                <table role="presentation" width="100%" style="border-collapse:collapse;">
                    <tr>
                        <td style="vertical-align:middle;">
                            <p style="margin:0 0 4px;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;opacity:0.8;">💎 GeM Scraper</p>
                            <h1 style="margin:0;font-size:21px;font-weight:800;letter-spacing:-0.01em;">Tender Digest</h1>
                            <p style="margin:6px 0 0;font-size:12px;opacity:0.82;">{now}</p>
                        </td>
                        <td align="right" style="vertical-align:middle;">
                            <div style="display:inline-block;background:rgba(255,255,255,0.18);border-radius:12px;padding:10px 16px;text-align:center;">
                                <div style="font-size:26px;font-weight:800;line-height:1;">{total_new}</div>
                                <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.06em;opacity:0.9;margin-top:3px;">new tender{plural}</div>
                            </div>
                        </td>
                    </tr>
                </table>
            </div>

            <!-- Stats Bar -->
            <table role="presentation" width="100%" style="border-collapse:collapse;background:#fafafb;border-bottom:1px solid #eeeef1;">
                <tr>
                    {stat_cell(stats['total_tenders'], 'Total', '#1a1a1f')}
                    {stat_cell(len(gujarat_tenders), 'Gujarat', GREEN)}
                    {stat_cell(len(other_tenders), 'Others', BLUE)}
                    {stat_cell(stats['relevant_links'], 'Rel. Links', AMBER)}
                </tr>
            </table>

            <!-- Tender Sections -->
            <div style="padding:24px 18px 4px;">
                {gujarat_section}
                {other_section}
            </div>

            <!-- Footer -->
            <div style="padding:8px 28px 28px;text-align:center;">
                <a href="{DASHBOARD_URL}" style="display:inline-block;padding:12px 28px;background:{RED};color:#ffffff;border-radius:9px;text-decoration:none;font-weight:700;font-size:14px;">Open Dashboard →</a>
            </div>
        </div>
        <p style="margin:16px 0 0;text-align:center;font-size:11px;color:#aab;">GeM Scraper · Event / Seminar / Workshop · Tentage Service tenders</p>
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
