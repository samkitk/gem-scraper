"""
Gemini AI Summarizer for GeM Tender Documents.
Uses Google Gemini API to generate structured summaries and classify uncertain links.
"""
import json
import time
import logging
import google.generativeai as genai

import config

logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=config.GEMINI_API_KEY)


def get_model():
    """Get a configured Gemini model instance."""
    return genai.GenerativeModel(
        config.GEMINI_MODEL,
        generation_config={
            "temperature": 0.2,
            "max_output_tokens": 4096,
        }
    )


def summarize_tender(text: str, bid_number: str = "") -> dict:
    """
    Generate a structured summary of a tender document.
    Returns a dict with summary, scope_of_work, eligibility, key_dates, etc.
    """
    if not text or len(text.strip()) < 100:
        logger.warning(f"Text too short to summarize for {bid_number}")
        return {"summary": "Insufficient text in PDF", "error": "text_too_short"}

    prompt = f"""You are an expert at analyzing Indian Government e-Marketplace (GeM) tender documents.
Analyze the following tender document text (which may include attached scope-of-work documents) and extract key information.

TENDER DOCUMENT TEXT:
---
{text[:25000]}
---

Return a JSON object with the following fields (use null if information is not found):
{{
    "title": "Brief title of the tender",
    "summary": "2-3 sentence summary of what this tender is about",
    "department": "Full department/organization name",
    "scope_of_work": "Detailed description of the scope of work - include all deliverables, event details, specifications from attached SOW documents",
    "estimated_value": "Estimated bid value or budget (include currency)",
    "budget_range": "Budget range if mentioned",
    "eligibility": "Key eligibility criteria for bidders",
    "key_dates": {{
        "bid_start": "Bid start date",
        "bid_end": "Bid end date/deadline",
        "event_date": "Event/delivery date if applicable",
        "pre_bid_meeting": "Pre-bid meeting date if any"
    }},
    "location": "City and State where event/work will happen (e.g. 'Ahmedabad, Gujarat' or 'New Delhi'). Extract from department address or event venue.",
    "state": "Indian state name only (e.g. 'Gujarat', 'Maharashtra', 'Delhi')",
    "contact_info": "Contact person, phone, email if available",
    "key_requirements": ["List of key requirements or deliverables"],
    "special_conditions": "Any special terms or conditions worth noting",
    "payment_terms": "Payment terms if mentioned",
    "category": "Type of event/service required"
}}

IMPORTANT: Return ONLY valid JSON, no markdown formatting or extra text."""


    max_retries = 3
    for attempt in range(max_retries):
        try:
            model = get_model()
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Clean up response - remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[1]
            if response_text.endswith("```"):
                response_text = response_text.rsplit("```", 1)[0]
            response_text = response_text.strip()
            
            result = json.loads(response_text)
            logger.info(f"Successfully summarized tender {bid_number}")
            
            # Flatten key_dates to a string for DB storage
            if isinstance(result.get("key_dates"), dict):
                dates_str = " | ".join(
                    f"{k}: {v}" for k, v in result["key_dates"].items() if v
                )
                result["key_dates"] = dates_str

            # Convert list fields to strings
            if isinstance(result.get("key_requirements"), list):
                result["key_requirements"] = " | ".join(result["key_requirements"])
                
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            logger.debug(f"Raw response: {response_text[:500]}")
            return {
                "summary": response_text[:500] if response_text else "Failed to parse",
                "error": "json_parse_error",
            }
        except Exception as e:
            error_str = str(e)
            if "429" in error_str and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 10  # 10s, 20s, 30s
                logger.warning(f"Rate limited on {bid_number}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            logger.error(f"Gemini API error for {bid_number}: {e}")
            return {"summary": f"Error: {error_str}", "error": error_str}


def classify_uncertain_links(links: list[dict], tender_summary: str = "") -> list[dict]:
    """
    Use Gemini to classify links that couldn't be determined by heuristics.
    """
    if not links:
        return links

    links_text = "\n".join(
        f"- URL: {l['url']}\n  Context: {(l.get('link_text', '') or '')[:150]}"
        for l in links
    )

    prompt = f"""You are analyzing hyperlinks extracted from an Indian Government tender document (GeM portal).

TENDER CONTEXT: {tender_summary[:500] if tender_summary else 'Event/Seminar/Workshop tender'}

LINKS TO CLASSIFY:
{links_text}

For each link, determine if it is RELEVANT (contains scope of work, specifications, BOQ, technical documents, 
important attachments, Excel files, or other essential tender information) or IRRELEVANT (generic pages, 
terms & conditions, login pages, or unrelated content).

Return a JSON array where each element has:
{{
    "url": "the URL",
    "is_relevant": true/false,
    "reason": "brief reason"
}}

Return ONLY valid JSON array, no extra text."""

    try:
        model = get_model()
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean up
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1]
        if response_text.endswith("```"):
            response_text = response_text.rsplit("```", 1)[0]
        
        classifications = json.loads(response_text.strip())
        
        # Map back to original links
        url_map = {c["url"]: c for c in classifications}
        for link in links:
            if link["url"] in url_map:
                c = url_map[link["url"]]
                link["is_relevant"] = c.get("is_relevant", False)
                link["link_type"] = "ai_classified"
                link["description"] = c.get("reason", "")

        return links

    except Exception as e:
        logger.error(f"Failed to classify links with Gemini: {e}")
        # Default uncertain links to relevant to not miss anything
        for link in links:
            if link.get("is_relevant") is None:
                link["is_relevant"] = True
                link["link_type"] = "ai_fallback_relevant"
        return links


def generate_summary_markdown(tender_data: dict, summary: dict) -> str:
    """Generate a nice markdown summary file for a tender."""
    md = f"""# {summary.get('title', tender_data.get('bid_number', 'Tender'))}

**Bid Number:** {tender_data.get('bid_number', 'N/A')}  
**Department:** {summary.get('department', tender_data.get('department', 'N/A'))}  
**Category:** {summary.get('category', 'Event / Seminar / Workshop')}  
**Estimated Value:** {summary.get('estimated_value', 'Not specified')}  
**Location:** {summary.get('location', 'Not specified')}

---

## Summary
{summary.get('summary', 'No summary available.')}

## Scope of Work
{summary.get('scope_of_work', 'Not specified in document.')}

## Key Dates
{summary.get('key_dates', 'Not specified')}

## Eligibility Criteria
{summary.get('eligibility', 'Not specified.')}

## Key Requirements
{summary.get('key_requirements', 'Not specified.')}

## Budget / Payment
- **Budget Range:** {summary.get('budget_range', 'Not specified')}
- **Payment Terms:** {summary.get('payment_terms', 'Not specified')}

## Special Conditions
{summary.get('special_conditions', 'None noted.')}

## Contact Information
{summary.get('contact_info', 'Not specified.')}

---
*Auto-generated by GeM Scraper on {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
    return md
