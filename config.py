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

# Categories to scrape: GeM dropdown option value -> human-readable label.
# The label is stored on each tender so the dashboard shows the correct category.
CATEGORY_VALUES = {
    "services_home_ev80610203_even": "Event Or Seminar Or Workshop Or Exhibition Or Expo Management Service",
    "services_home_tent": "Tentage Service - Pole Tents",
    "services_home_te45240781": "Tentage Service Lumpsum Based",
}

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


def get_commit_sha() -> str:
    """Helper to get the current Git commit SHA (either from environment, build-file, or git command)."""
    # 1. Environment variable
    sha = os.getenv("COMMIT_SHA")
    if sha and sha != "unknown":
        return sha[:7]

    # 2. Build-time commit_sha.txt file
    sha_file = BASE_DIR / "commit_sha.txt"
    if sha_file.exists():
        try:
            file_sha = sha_file.read_text(encoding="utf-8").strip()
            if file_sha and file_sha != "unknown":
                return file_sha[:7]
        except Exception:
            pass

    # 3. Local git repository (for development)
    try:
        import subprocess
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return res.stdout.strip()
    except Exception:
        pass

    return "unknown"

