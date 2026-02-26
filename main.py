"""
GeM Tender Scraper - Main Orchestrator
Runs the full pipeline: scrape → download → parse → summarize
"""
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime

import config
import db
from scraper import GemScraper
from pdf_downloader import download_all_pdfs, download_attachment, get_tender_folder
from pdf_parser import parse_tender_pdf
from summarizer import summarize_tender, classify_uncertain_links, generate_summary_markdown

# ── Logging Setup ──
logging.basicConfig(
    level=logging.INFO,
    format=config.LOG_FORMAT,
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("gem-scraper")


def step_scrape() -> list[dict]:
    """Step 1: Scrape bid listings from GeM portal."""
    logger.info("=" * 60)
    logger.info("STEP 1: Scraping GeM portal for tender listings...")
    logger.info("=" * 60)

    scraper = GemScraper()
    tenders = scraper.scrape_all()

    new_count = 0
    for tender in tenders:
        if not db.tender_exists(tender["bid_number"]):
            new_count += 1

    logger.info(f"Found {len(tenders)} tenders ({new_count} new)")
    return tenders


def step_save_and_download(tenders: list[dict]) -> list[dict]:
    """Step 2: Save to DB and download PDFs."""
    logger.info("=" * 60)
    logger.info("STEP 2: Saving tenders to DB & downloading PDFs...")
    logger.info("=" * 60)

    # Download PDFs
    tenders = download_all_pdfs(tenders)

    # Save to DB
    new_count = 0
    for tender in tenders:
        row_id = db.insert_tender(tender)
        if row_id > 0:
            new_count += 1
            logger.info(f"  NEW: {tender['bid_number']} (id={row_id})")
        else:
            logger.debug(f"  SKIP (exists): {tender['bid_number']}")

    logger.info(f"Saved {new_count} new tenders to database")
    return tenders


def step_process(tender_id: str = None):
    """Step 3: Process unprocessed tenders (parse PDFs + summarize with Gemini)."""
    logger.info("=" * 60)
    logger.info("STEP 3: Processing tenders (PDF parsing + Gemini summarization)...")
    logger.info("=" * 60)

    if tender_id:
        tender = db.get_tender_by_bid(tender_id)
        if not tender:
            logger.error(f"Tender not found: {tender_id}")
            return
        unprocessed = [tender]
    else:
        unprocessed = db.get_unprocessed_tenders()

    if not unprocessed:
        logger.info("No unprocessed tenders found.")
        return

    logger.info(f"Processing {len(unprocessed)} tenders...")

    for i, tender in enumerate(unprocessed):
        bid_num = tender["bid_number"]
        pdf_path = tender.get("pdf_path")

        logger.info(f"\n[{i+1}/{len(unprocessed)}] Processing {bid_num}")

        if not pdf_path or not Path(pdf_path).exists():
            logger.warning(f"  PDF not found for {bid_num}, skipping")
            continue

        # ── Parse main tender PDF ──
        logger.info(f"  Parsing PDF: {pdf_path}")
        parsed = parse_tender_pdf(pdf_path)
        text = parsed["text"]
        all_links = parsed["all_links"]
        relevant_links = parsed["relevant_links"]
        uncertain_links = parsed["uncertain_links"]

        logger.info(
            f"  Found {parsed['total_links']} links "
            f"({parsed['relevant_count']} relevant, {len(uncertain_links)} uncertain)"
        )

        # ── Download relevant attachments FIRST ──
        folder = get_tender_folder(bid_num)
        attachment_texts = []
        if relevant_links:
            logger.info(f"  Downloading {len(relevant_links)} relevant attachments...")
            for link in relevant_links:
                if link.get("url"):
                    local = download_attachment(link["url"], folder)
                    # Extract text from downloaded PDFs for the combined summary
                    if local and Path(local).suffix.lower() == ".pdf" and Path(local).exists():
                        try:
                            from pdf_parser import extract_text as extract_pdf_text
                            att_text = extract_pdf_text(str(local))
                            if att_text and len(att_text.strip()) > 50:
                                attachment_texts.append(att_text)
                                logger.info(f"    Extracted text from attachment: {Path(local).name} ({len(att_text)} chars)")
                        except Exception as e:
                            logger.debug(f"    Could not extract text from {local}: {e}")

        # ── Combine tender text with attachment texts ──
        combined_text = text
        if attachment_texts:
            combined_text += "\n\n--- SCOPE OF WORK / ATTACHED DOCUMENTS ---\n\n"
            combined_text += "\n\n---\n\n".join(attachment_texts)
            logger.info(f"  Combined text: {len(text)} (tender) + {sum(len(t) for t in attachment_texts)} (attachments) chars")

        # ── Summarize with Gemini (using combined text) ──
        logger.info(f"  Summarizing with Gemini API...")
        summary = summarize_tender(combined_text, bid_num)

        if summary.get("error"):
            logger.warning(f"  Summary had issues: {summary.get('error')}")

        # ── Classify uncertain links with Gemini ──
        if uncertain_links:
            logger.info(f"  Classifying {len(uncertain_links)} uncertain links with Gemini...")
            classified = classify_uncertain_links(
                uncertain_links,
                summary.get("summary", "")
            )
            for link in classified:
                if link.get("is_relevant"):
                    relevant_links.append(link)

        # ── Save links to DB ──
        tender_row = db.get_tender_by_bid(bid_num)
        if tender_row:
            db.insert_links(tender_row["id"], all_links)

        # ── Update DB with processing results ──
        db.update_tender_processing(bid_num, {
            "summary": summary.get("summary"),
            "scope_of_work": summary.get("scope_of_work"),
            "eligibility": summary.get("eligibility"),
            "key_dates": summary.get("key_dates"),
            "budget_range": summary.get("budget_range"),
            "contact_info": summary.get("contact_info"),
            "estimated_value": summary.get("estimated_value"),
            "location": summary.get("location"),
        })

        # ── Generate summary markdown ──
        md_content = generate_summary_markdown(tender, summary)
        summary_path = folder / "summary.md"
        summary_path.write_text(md_content, encoding="utf-8")
        logger.info(f"  Summary saved: {summary_path}")

        # ── Save links JSON ──
        links_path = folder / "links.json"
        links_path.write_text(
            json.dumps(all_links, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        logger.info(f"  ✓ Completed processing {bid_num}")

        # Rate limit Gemini API calls
        if i < len(unprocessed) - 1:
            time.sleep(3)



def run_full_pipeline():
    """Run the complete pipeline: scrape → download → process."""
    start_time = datetime.now()
    logger.info(f"\n{'#' * 60}")
    logger.info(f"GeM Scraper - Full Pipeline Run")
    logger.info(f"Started at: {start_time.isoformat()}")
    logger.info(f"{'#' * 60}\n")

    try:
        # Step 1: Scrape
        tenders = step_scrape()

        if not tenders:
            logger.warning("No tenders found. Check if the portal is accessible.")
            db.log_scrape_run(0, 0, "no_results")
            return

        # Step 2: Save & Download
        tenders = step_save_and_download(tenders)
        new_count = sum(1 for t in tenders if not db.tender_exists(t["bid_number"]))

        # Step 3: Process
        step_process()

        # Log the run
        db.log_scrape_run(new_count, len(tenders))

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        db.log_scrape_run(0, 0, "error", str(e))

    elapsed = datetime.now() - start_time
    logger.info(f"\nPipeline completed in {elapsed.total_seconds():.1f} seconds")

    # Print stats
    stats = db.get_tender_stats()
    logger.info(f"\n📊 Database Stats:")
    logger.info(f"  Total tenders: {stats['total_tenders']}")
    logger.info(f"  Processed: {stats['processed']}")
    logger.info(f"  Unprocessed: {stats['unprocessed']}")
    logger.info(f"  Total links: {stats['total_links']}")
    logger.info(f"  Relevant links: {stats['relevant_links']}")


def show_stats():
    """Show database statistics."""
    stats = db.get_tender_stats()
    print(f"\n📊 GeM Scraper Database Stats")
    print(f"{'─' * 40}")
    print(f"  Total tenders:  {stats['total_tenders']}")
    print(f"  Processed:      {stats['processed']}")
    print(f"  Unprocessed:    {stats['unprocessed']}")
    print(f"  Total links:    {stats['total_links']}")
    print(f"  Relevant links: {stats['relevant_links']}")
    print()

    # Show recent tenders
    recent = db.get_all_tenders(limit=10)
    if recent:
        print(f"📋 Recent Tenders (last 10):")
        print(f"{'─' * 80}")
        for t in recent:
            status = "✅" if t["processed"] else "⏳"
            print(f"  {status} {t['bid_number']:30s} | {(t['department'] or 'N/A'):30s} | {(t['end_date'] or 'N/A')}")
    print()


def main():
    parser = argparse.ArgumentParser(description="GeM Portal Tender Scraper")
    parser.add_argument("--scrape-only", action="store_true",
                        help="Only scrape listings, don't download or process")
    parser.add_argument("--download-only", action="store_true",
                        help="Only download PDFs for existing unprocessed tenders")
    parser.add_argument("--process-only", action="store_true",
                        help="Only process already-downloaded PDFs with Gemini")
    parser.add_argument("--tender", type=str,
                        help="Process a specific tender by bid number (e.g. GEM/2026/B/7244758)")
    parser.add_argument("--stats", action="store_true",
                        help="Show database statistics")
    parser.add_argument("--list", action="store_true",
                        help="List all tenders in the database")
    
    args = parser.parse_args()

    if args.stats or args.list:
        show_stats()
        return

    if args.scrape_only:
        tenders = step_scrape()
        print(f"\nScraped {len(tenders)} tenders")
        return

    if args.process_only or args.tender:
        step_process(args.tender)
        return

    if args.download_only:
        unprocessed = db.get_unprocessed_tenders()
        if unprocessed:
            download_all_pdfs(unprocessed)
        else:
            print("No unprocessed tenders to download.")
        return

    # Default: run full pipeline
    run_full_pipeline()


if __name__ == "__main__":
    main()
