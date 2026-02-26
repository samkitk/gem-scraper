"""
PDF Downloader for GeM Tender Documents.
Downloads tender PDFs and organizes them into per-tender folders.
"""
import time
import logging
import requests
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def get_tender_folder(bid_number: str) -> Path:
    """Create and return the folder path for a tender."""
    # Sanitize bid number for folder name: GEM/2026/B/7244758 -> GEM-2026-B-7244758
    folder_name = bid_number.replace("/", "-")
    folder = config.TENDERS_DIR / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    
    # Create attachments subfolder
    (folder / "attachments").mkdir(exist_ok=True)
    
    return folder


def download_pdf(document_id: str, bid_number: str, session: requests.Session = None) -> str | None:
    """
    Download a tender PDF from GeM portal.
    Returns the local file path if successful, None otherwise.
    """
    if session is None:
        session = requests.Session()
        session.headers.update(config.HEADERS)

    # Create tender folder
    folder = get_tender_folder(bid_number)
    pdf_path = folder / "tender.pdf"
    
    # Also save a copy in the central pdfs dir
    central_pdf = config.PDF_DIR / f"{bid_number.replace('/', '-')}.pdf"

    # Skip if already downloaded
    if pdf_path.exists() and pdf_path.stat().st_size > 0:
        logger.info(f"PDF already exists: {pdf_path}")
        return str(pdf_path)

    url = f"{config.GEM_BID_DOC_URL}/{document_id}"
    logger.info(f"Downloading PDF: {url}")

    try:
        resp = session.get(url, timeout=60, stream=True)
        resp.raise_for_status()

        # Verify it's actually a PDF
        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower() and not resp.content[:5] == b"%PDF-":
            logger.warning(f"Response is not a PDF (Content-Type: {content_type})")
            # Save anyway, might still be valid
            if len(resp.content) < 1000:
                logger.error(f"Response too small ({len(resp.content)} bytes), likely an error page")
                return None

        # Save PDF to tender folder
        with open(pdf_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        # Also copy to central PDF directory
        if not central_pdf.exists():
            import shutil
            shutil.copy2(pdf_path, central_pdf)

        file_size = pdf_path.stat().st_size
        logger.info(f"Downloaded PDF ({file_size:,} bytes): {pdf_path}")
        return str(pdf_path)

    except requests.RequestException as e:
        logger.error(f"Failed to download PDF for {bid_number}: {e}")
        return None


def download_attachment(url: str, tender_folder: Path, filename: str = None,
                        session: requests.Session = None) -> str | None:
    """
    Download an attachment (Excel, Word, etc.) from a URL.
    Returns local path if successful.
    """
    if session is None:
        session = requests.Session()
        session.headers.update(config.HEADERS)

    attachments_dir = tender_folder / "attachments"
    attachments_dir.mkdir(exist_ok=True)

    # Determine filename
    if not filename:
        from urllib.parse import urlparse, unquote
        parsed = urlparse(url)
        filename = unquote(parsed.path.split("/")[-1]) or "attachment"

    # Sanitize filename
    filename = "".join(c if c.isalnum() or c in ".-_ " else "_" for c in filename)
    filepath = attachments_dir / filename

    # Skip if already downloaded
    if filepath.exists() and filepath.stat().st_size > 0:
        logger.info(f"Attachment already exists: {filepath}")
        return str(filepath)

    try:
        resp = session.get(url, timeout=30, stream=True)
        resp.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"Downloaded attachment: {filepath}")
        return str(filepath)

    except requests.RequestException as e:
        logger.warning(f"Failed to download attachment {url}: {e}")
        return None


def download_all_pdfs(tenders: list[dict]) -> list[dict]:
    """
    Download PDFs for all tenders.
    Returns updated tender dicts with pdf_path and folder_path set.
    """
    session = requests.Session()
    session.headers.update(config.HEADERS)
    
    # First, load the search page to get session cookies
    try:
        session.get(config.GEM_SEARCH_URL, timeout=30)
    except Exception:
        pass

    results = []
    for i, tender in enumerate(tenders):
        doc_id = tender.get("document_id")
        bid_num = tender.get("bid_number")
        
        if not doc_id or not bid_num:
            logger.warning(f"Skipping tender without doc_id or bid_number: {tender}")
            results.append(tender)
            continue

        logger.info(f"[{i+1}/{len(tenders)}] Downloading {bid_num} (doc: {doc_id})")
        
        pdf_path = download_pdf(doc_id, bid_num, session)
        folder = get_tender_folder(bid_num)
        
        tender["pdf_path"] = pdf_path
        tender["folder_path"] = str(folder)
        results.append(tender)

        # Be polite
        if i < len(tenders) - 1:
            time.sleep(config.REQUEST_DELAY)

    return results
