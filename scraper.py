"""
GeM Portal Scraper (Selenium-based)
Scrapes bid listings from the GeM advanced search page using a headless browser
to handle CSRF tokens, cookies, and JavaScript-rendered content.
"""
import re
import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException,
    WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager

import config

logger = logging.getLogger(__name__)


class GemScraper:
    """Scrapes the GeM portal for Event/Seminar/Workshop tenders using Selenium."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None

    def _init_driver(self):
        """Initialize Chrome WebDriver."""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(
            f"--user-agent={config.HEADERS['User-Agent']}"
        )
        # Disable automation detection
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception:
            # Fallback: try without webdriver_manager
            self.driver = webdriver.Chrome(options=chrome_options)

        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self.driver.implicitly_wait(5)
        logger.info("Chrome WebDriver initialized")

    def _close_driver(self):
        """Close the WebDriver."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def _search_category(self, category_value: str):
        """Navigate to search page and select a category."""
        logger.info("Loading GeM advanced search page...")
        self.driver.get(config.GEM_SEARCH_URL)
        time.sleep(3)

        # Wait for the page to load
        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "categorybid"))
            )
        except TimeoutException:
            logger.error("Search page failed to load")
            raise

        # The category dropdown is a Select2 widget. We need to set it via JS.
        logger.info(f"Setting category to: {category_value}")

        # Use JavaScript to set the Select2 value (since it's a styled dropdown)
        self.driver.execute_script(f"""
            var select = document.getElementById('categorybid');
            var option = document.querySelector('option[value="{category_value}"]');
            if (option) {{
                option.selected = true;
                select.value = '{category_value}';
                // Trigger change event for Select2
                var event = new Event('change', {{ bubbles: true }});
                select.dispatchEvent(event);
                if (typeof $ !== 'undefined' && $.fn.trigger) {{
                    $('#categorybid').trigger('change');
                }}
            }}
        """)
        time.sleep(1)

        # Click the search button
        logger.info("Clicking search button...")
        try:
            search_btn = self.driver.find_element(By.ID, "searchByBid")
            search_btn.click()
        except NoSuchElementException:
            # Try alternative selectors
            search_btn = self.driver.find_element(
                By.CSS_SELECTOR, "a.search, button.search, input[type='submit']"
            )
            search_btn.click()

        # Wait for results to load
        time.sleep(4)
        logger.info("Search results loading...")

    def _get_current_page_tenders(self) -> list[dict]:
        """Parse tender listings from the current page."""
        tenders = []

        # Wait for results to appear
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "a[href*='showbidDocument']")
                )
            )
        except TimeoutException:
            logger.warning("No bid results found on this page")
            # Check if there's a "no results" message
            page_text = self.driver.page_source
            if "no record" in page_text.lower() or "0 records" in page_text.lower():
                logger.info("No records found for this search")
            return []

        # Find all bid document links
        bid_links = self.driver.find_elements(
            By.CSS_SELECTOR, "a[href*='showbidDocument']"
        )

        for link in bid_links:
            try:
                tender = self._extract_tender_from_link(link)
                if tender and tender.get("bid_number"):
                    tenders.append(tender)
            except StaleElementReferenceException:
                continue
            except Exception as e:
                logger.warning(f"Error parsing tender: {e}")
                continue

        return tenders

    def _extract_tender_from_link(self, link_element) -> dict | None:
        """Extract tender data from a bid link and its parent block."""
        try:
            tender = {}

            # Get bid number from link text
            bid_number = link_element.text.strip()
            href = link_element.get_attribute("href") or ""

            if not bid_number:
                return None

            tender["bid_number"] = bid_number

            # Extract document ID from URL
            doc_match = re.search(r"showbidDocument/(\d+)", href)
            if doc_match:
                tender["document_id"] = doc_match.group(1)

            # Navigate up to the parent block/card to get more context
            try:
                # Go up several levels to find the result block
                block = link_element.find_element(By.XPATH, "./ancestor::div[contains(@class,'block') or contains(@class,'card') or contains(@class,'border')]")
                block_text = block.text
            except NoSuchElementException:
                # Fallback: get parent div text
                try:
                    block = link_element.find_element(By.XPATH, "./ancestor::div[4]")
                    block_text = block.text
                except Exception:
                    block_text = ""

            if block_text:
                # Extract items / category
                items_match = re.search(r"Items?:\s*(.+?)(?:\n|$)", block_text, re.I)
                if items_match:
                    tender["items"] = items_match.group(1).strip()

                # Quantity
                qty_match = re.search(r"Quantity:\s*(\d+)", block_text, re.I)
                if qty_match:
                    tender["quantity"] = qty_match.group(1)

                # Department
                dept_match = re.search(
                    r"Department\s*Name\s*(?:And|&)\s*Address:\s*\n?\s*(.+?)(?:\n.*?Start\s*Date|$)",
                    block_text, re.I | re.DOTALL
                )
                if dept_match:
                    dept_lines = [
                        l.strip() for l in dept_match.group(1).strip().split("\n")
                        if l.strip() and "Start Date" not in l and "End Date" not in l
                    ]
                    tender["department"] = dept_lines[0] if dept_lines else ""
                    tender["department_address"] = " | ".join(dept_lines[1:]) if len(dept_lines) > 1 else ""

                # Dates
                start_match = re.search(
                    r"Start\s*Date:\s*(.+?)(?:\n|End|$)", block_text, re.I
                )
                if start_match:
                    tender["start_date"] = start_match.group(1).strip()

                end_match = re.search(
                    r"End\s*Date:\s*(.+?)(?:\n|$)", block_text, re.I
                )
                if end_match:
                    tender["end_date"] = end_match.group(1).strip()

                # Estimated value
                value_match = re.search(
                    r"(?:Estimated|Total)\s*(?:Bid)?\s*Value:\s*(?:Rs\.?|₹|INR)?\s*([\d,\.]+)",
                    block_text, re.I
                )
                if value_match:
                    tender["estimated_value"] = value_match.group(1).strip()

            tender["category"] = "Event Or Seminar Or Workshop"
            return tender

        except Exception as e:
            logger.warning(f"Failed to extract tender: {e}")
            return None

    def _get_total_records(self) -> int:
        """Get total number of records from the results page."""
        try:
            # Look for "Showing X - Y of Z records"
            page_source = self.driver.page_source
            match = re.search(r"of\s+(\d+)\s+records", page_source, re.I)
            if match:
                return int(match.group(1))
        except Exception as e:
            logger.warning(f"Could not determine total records: {e}")
        return 0

    def _go_to_next_page(self) -> bool:
        """Navigate to the next page of results. Returns True if successful."""
        try:
            # GeM uses #light-pagination with a.page-link.next for the Next button
            next_btn = self.driver.find_elements(
                By.CSS_SELECTOR, "#light-pagination a.page-link.next"
            )
            if next_btn:
                # Grab the first bid number before clicking to verify page changed
                old_bids = [
                    a.text.strip()
                    for a in self.driver.find_elements(
                        By.CSS_SELECTOR, "a[href*='showbidDocument']"
                    )[:1]
                ]

                next_btn[0].click()
                time.sleep(3)

                # Verify content actually changed
                new_bids = [
                    a.text.strip()
                    for a in self.driver.find_elements(
                        By.CSS_SELECTOR, "a[href*='showbidDocument']"
                    )[:1]
                ]
                if new_bids and new_bids != old_bids:
                    return True
                elif new_bids:
                    # Content may not have changed, but we still got results
                    return True

            logger.debug("No 'Next' button found in #light-pagination")
        except Exception as e:
            logger.debug(f"Next page navigation failed: {e}")

        return False

    def _navigate_page_by_js(self, page_num: int) -> bool:
        """Navigate to a specific page by clicking its page-link in #light-pagination."""
        try:
            # Click the specific page number link
            page_links = self.driver.find_elements(
                By.CSS_SELECTOR, f"#light-pagination a.page-link[href='#page-{page_num}']"
            )
            if page_links:
                page_links[0].click()
                time.sleep(3)
                return True

            # Fallback: try clicking 'Next' button repeatedly from current page
            current_span = self.driver.find_elements(
                By.CSS_SELECTOR, "#light-pagination span.current"
            )
            if current_span:
                current = int(current_span[0].text.strip())
                if current < page_num:
                    return self._go_to_next_page()

        except Exception as e:
            logger.debug(f"JS page navigation failed: {e}")
        return False

    def scrape_all(self) -> list[dict]:
        """Scrape all tenders across all categories and pages."""
        all_tenders = []

        try:
            self._init_driver()

            for category in config.CATEGORY_VALUES:
                logger.info(f"Scraping category: {category}")

                try:
                    self._search_category(category)
                    total_records = self._get_total_records()
                    logger.info(f"Total records found: {total_records}")

                    # Scrape first page
                    page_num = 1
                    tenders = self._get_current_page_tenders()
                    all_tenders.extend(tenders)
                    logger.info(f"Page {page_num}: found {len(tenders)} tenders")

                    # Calculate total pages
                    total_pages = (total_records + config.RESULTS_PER_PAGE - 1) // config.RESULTS_PER_PAGE if total_records > 0 else 1

                    # Scrape remaining pages
                    while page_num < total_pages:
                        page_num += 1
                        logger.info(f"Navigating to page {page_num}/{total_pages}")

                        if self._go_to_next_page():
                            tenders = self._get_current_page_tenders()
                            all_tenders.extend(tenders)
                            logger.info(f"Page {page_num}: found {len(tenders)} tenders")
                        elif self._navigate_page_by_js(page_num):
                            tenders = self._get_current_page_tenders()
                            all_tenders.extend(tenders)
                            logger.info(f"Page {page_num} (JS): found {len(tenders)} tenders")
                        else:
                            logger.warning(f"Could not navigate to page {page_num}, stopping")
                            break

                        time.sleep(config.REQUEST_DELAY)

                except Exception as e:
                    logger.error(f"Failed to scrape category {category}: {e}", exc_info=True)
                    continue

        finally:
            self._close_driver()

        # Deduplicate by bid number
        seen = set()
        unique_tenders = []
        for t in all_tenders:
            bid = t.get("bid_number")
            if bid and bid not in seen:
                seen.add(bid)
                unique_tenders.append(t)

        logger.info(f"Total unique tenders scraped: {len(unique_tenders)}")
        return unique_tenders


def scrape() -> list[dict]:
    """Convenience function to run the scraper."""
    scraper = GemScraper()
    return scraper.scrape_all()
