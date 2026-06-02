"""
Configuration for GeM Portal Scraper
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdfs"
TENDERS_DIR = DATA_DIR / "tenders"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "gem_tenders.db"

# Create directories
for d in [DATA_DIR, PDF_DIR, TENDERS_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── GeM Portal ──
GEM_BASE_URL = "https://bidplus.gem.gov.in"
GEM_SEARCH_URL = f"{GEM_BASE_URL}/advance-search"
GEM_BID_DOC_URL = f"{GEM_BASE_URL}/showbidDocument"

# Category values for Event/Seminar/Workshop
CATEGORY_VALUES = [
    "services_home_ev80610203_even",  # Event Or Seminar Or Workshop Or Exhibition Or Expo Management Service
]

# HTTP headers to mimic a real browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": GEM_SEARCH_URL,
    "Connection": "keep-alive",
}

# ── Gemini API ──
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-3.5-flash"

# ── Scraper Settings ──
SCRAPE_INTERVAL_MINUTES = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "60"))
RESULTS_PER_PAGE = 10
REQUEST_DELAY = 2  # seconds between requests to be polite

# ── Email (Resend) ──
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "GeM Scraper <gems@updates.aumevent.com>")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://gem.aumevent.com")

# ── Logging ──
LOG_FILE = LOG_DIR / "scraper.log"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
