"""
Cron Job Runner for GeM Scraper.
Runs the scraper at configurable intervals and sends email digests.
"""
import sys
import time
import logging
import schedule

import config
from main import run_full_pipeline, show_stats
from email_digest import send_digest

logging.basicConfig(
    level=logging.INFO,
    format=config.LOG_FORMAT,
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("gem-cron")


def job():
    """Run the full scraping pipeline, then send email digest."""
    logger.info("⏰ Cron job triggered - running full pipeline...")
    try:
        run_full_pipeline()
    except Exception as e:
        logger.error(f"Cron job failed: {e}", exc_info=True)

    # Send email digest after each run
    try:
        send_digest()
    except Exception as e:
        logger.error(f"Email digest failed: {e}", exc_info=True)

    logger.info("⏰ Cron job completed.\n")


def main():
    interval = config.SCRAPE_INTERVAL_MINUTES
    logger.info(f"🚀 GeM Scraper Cron Runner started")
    logger.info(f"   Interval: every {interval} minutes")
    logger.info(f"   Press Ctrl+C to stop\n")

    # Run immediately on start
    job()

    # Schedule recurring runs
    schedule.every(interval).minutes.do(job)

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("\n🛑 Cron runner stopped by user")
        show_stats()


if __name__ == "__main__":
    main()
