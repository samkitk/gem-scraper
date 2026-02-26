"""
PDF Parser for GeM Tender Documents.
Extracts text and hyperlinks from tender PDFs.
"""
import re
import logging
from pathlib import Path
from urllib.parse import urlparse

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Links that are generally irrelevant (generic govt/GeM pages)
IRRELEVANT_DOMAINS = {
    "gem.gov.in",
    "www.gem.gov.in", 
    "mkp.gem.gov.in",
    "assets-bg.gem.gov.in",
    "google.com",
    "fonts.googleapis.com",
    "www.google.com",
}

IRRELEVANT_PATTERNS = [
    r"gem\.gov\.in/?$",
    r"gem\.gov\.in/terms",
    r"gem\.gov\.in/conditions",
    r"gem\.gov\.in/privacy",
    r"gem\.gov\.in/about",
    r"gem\.gov\.in/contact",
    r"gem\.gov\.in/help",
    r"gem\.gov\.in/faq",
    r"gem\.gov\.in/grievance",
    r"javascript:",
    r"mailto:",
    r"tel:",
    r"#$",
]

# File extensions that indicate relevant attachments
RELEVANT_EXTENSIONS = {
    ".xlsx", ".xls", ".csv",
    ".doc", ".docx",
    ".pdf",
    ".zip", ".rar",
    ".ppt", ".pptx",
}

# Keywords that suggest a link is relevant (scope of work, specs, etc.)
RELEVANT_KEYWORDS = [
    "scope", "work", "specification", "spec", "requirement",
    "boq", "bill of quantity", "schedule", "annexure",
    "tender", "document", "corrigendum", "addendum",
    "drawing", "plan", "design", "layout",
    "excel", "download", "attachment", "enclosure",
    "nit", "notice inviting tender",
    "pre-qualification", "eligibility",
    "technical", "financial", "bid",
]


def extract_text(pdf_path: str) -> str:
    """Extract all text from a PDF."""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
        return text
    except Exception as e:
        logger.error(f"Failed to extract text from {pdf_path}: {e}")
        return ""


def extract_links(pdf_path: str) -> list[dict]:
    """Extract all hyperlinks from a PDF with their context."""
    links = []
    seen_urls = set()
    
    try:
        doc = fitz.open(pdf_path)
        
        for page_num, page in enumerate(doc):
            # Get links from annotations
            for link in page.get_links():
                url = link.get("uri", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                
                # Get surrounding text for context
                rect = link.get("from")
                context = ""
                if rect:
                    # Get text near the link
                    expanded_rect = fitz.Rect(
                        rect.x0 - 50, rect.y0 - 20,
                        rect.x1 + 200, rect.y1 + 20
                    )
                    context = page.get_text("text", clip=expanded_rect).strip()
                
                links.append({
                    "url": url,
                    "link_text": context or url,
                    "page": page_num + 1,
                    "is_relevant": None,  # To be classified
                    "link_type": None,
                })
            
            # Also extract URLs from text using regex
            page_text = page.get_text()
            url_pattern = re.compile(
                r'https?://[^\s<>"\')\]]+',
                re.IGNORECASE
            )
            for match in url_pattern.finditer(page_text):
                url = match.group().rstrip(".,;:)")
                if url not in seen_urls:
                    seen_urls.add(url)
                    # Get surrounding context
                    start = max(0, match.start() - 100)
                    end = min(len(page_text), match.end() + 100)
                    context = page_text[start:end].strip()
                    
                    links.append({
                        "url": url,
                        "link_text": context,
                        "page": page_num + 1,
                        "is_relevant": None,
                        "link_type": None,
                    })
        
        doc.close()
    except Exception as e:
        logger.error(f"Failed to extract links from {pdf_path}: {e}")
    
    logger.info(f"Extracted {len(links)} unique links from {pdf_path}")
    return links


def classify_link(link: dict) -> dict:
    """
    Classify a link as relevant or irrelevant using heuristics.
    Sets is_relevant and link_type fields.
    """
    url = link.get("url", "")
    text = (link.get("link_text", "") or "").lower()
    
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()
    except Exception:
        link["is_relevant"] = False
        link["link_type"] = "invalid"
        return link
    
    # Check if it's a GeM-related domain
    is_gem = any(domain.endswith(d) for d in IRRELEVANT_DOMAINS) or "gem.gov.in" in domain

    if is_gem:
        # ── Relevant GeM links: buyer-uploaded docs, bid docs, SLA docs ──
        gem_relevant_patterns = [
            "download",       # downloadBuyerDoc
            "biddoc",         # bidding/biddoc/ (buyer-uploaded scope-of-work)
            "upload_nas",     # resources/upload_nas/ (buyer-uploaded docs)
            "showbid",        # showbidDocument
            "slafds",         # SLA/ATC documents from fulfilment.gem.gov.in
        ]
        if any(kw in path or kw in url for kw in gem_relevant_patterns):
            link["is_relevant"] = True
            link["link_type"] = "gem_document"
            return link

        # ── Irrelevant GeM links: boilerplate, GTC, static assets ──
        link["is_relevant"] = False
        link["link_type"] = "generic_gem"
        return link
    
    # Check against irrelevant patterns
    for pattern in IRRELEVANT_PATTERNS:
        if re.search(pattern, url, re.I):
            link["is_relevant"] = False
            link["link_type"] = "irrelevant_pattern"
            return link
    
    # Check for relevant file extensions
    ext = Path(parsed.path).suffix.lower()
    if ext in RELEVANT_EXTENSIONS:
        link["is_relevant"] = True
        link["link_type"] = f"file_{ext.lstrip('.')}"
        return link
    
    # Check for relevant keywords in text or URL
    combined = f"{url} {text}".lower()
    for keyword in RELEVANT_KEYWORDS:
        if keyword in combined:
            link["is_relevant"] = True
            link["link_type"] = "keyword_match"
            return link
    
    # External links are potentially relevant (could be scope-of-work documents)
    if domain and "gov.in" in domain:
        link["is_relevant"] = True
        link["link_type"] = "government_link"
        return link
    
    # Default: mark as uncertain (will be reviewed by Gemini)
    link["is_relevant"] = None  # Uncertain
    link["link_type"] = "uncertain"
    return link


def classify_all_links(links: list[dict]) -> list[dict]:
    """Classify all links and return them."""
    for link in links:
        classify_link(link)
    
    relevant = sum(1 for l in links if l.get("is_relevant") is True)
    irrelevant = sum(1 for l in links if l.get("is_relevant") is False)
    uncertain = sum(1 for l in links if l.get("is_relevant") is None)
    
    logger.info(
        f"Link classification: {relevant} relevant, "
        f"{irrelevant} irrelevant, {uncertain} uncertain"
    )
    return links


def parse_tender_pdf(pdf_path: str) -> dict:
    """
    Full pipeline: extract text, links, and classify them.
    Returns a dict with text, all_links, relevant_links, etc.
    """
    text = extract_text(pdf_path)
    links = extract_links(pdf_path)
    classified = classify_all_links(links)
    
    relevant = [l for l in classified if l.get("is_relevant") is True]
    uncertain = [l for l in classified if l.get("is_relevant") is None]
    
    return {
        "text": text,
        "all_links": classified,
        "relevant_links": relevant,
        "uncertain_links": uncertain,
        "total_links": len(classified),
        "relevant_count": len(relevant),
    }
