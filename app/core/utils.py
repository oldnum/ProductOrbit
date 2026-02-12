from urllib.parse import urlparse, urlunparse, urljoin
from app.core.logger import logger
from datetime import datetime
import os
import re
import html

# Validate and normalize URL for a specific domain.
LANG_PREFIXES = ["ua", "ukr", "en", "ru"]

# Validate and normalize URL for a specific domain.
def validate_url(url: str, domain: str):
    logger.info("⚪ [utils][validate_url]: Validating URL: %s for domain %s.", url, domain)

    if not url:
        logger.error("🔴 [utils][validate_url]: URL is empty.")
        return url, None, None

    parsed_url = urlparse(url)
    
    if not parsed_url.netloc.endswith(domain):
        logger.error("🔴 [utils][validate_url]: URL is not from %s.", domain)
        return url, None, None

    path = parsed_url.path
    if not path.startswith("/"): path = f"/{path}"

    path_parts = [p for p in path.split("/") if p]
    if path_parts and path_parts[0].lower() in LANG_PREFIXES:
        path_parts = path_parts[1:]

    normalized_path = f"/" + "/".join(path_parts)

    slug = os.path.splitext(path_parts[-1])[0] if path_parts else ""

    normalized_url = urljoin(f"https://{domain}/", normalized_path.lstrip("/"))

    logger.info("🟢 [utils][validate_url]: URL: %s, Path: %s, Slug: %s.", normalized_url, normalized_path, slug)

    return normalized_url, normalized_path, slug

# Parse date to timestamp
def parse_date_to_ts(date_to_str: str) -> int | None:
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, "%Y-%m-%d")
            date_to_ts = int(date_to.timestamp())
            logger.info("🟢 [utils][parse_date_to_ts]: Date to: %s", date_to_str)
            return date_to_ts
        except Exception as e:
            logger.error("🔴 [utils][parse_date_to_ts]: Invalid date_to format: %s. Expected YYYY-MM-DD. Error: %s", date_to_str, e)
    return None

# Clean text from HTML tags and unescape HTML entities
def clean_text(text: str) -> str:
    if not text: return ""
    clean = re.sub(r'<[^>]+>', '', text)
    return html.unescape(clean).strip()