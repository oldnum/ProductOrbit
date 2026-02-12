import aiohttp
import asyncio
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from app.models.internal import BrainProductData, BrainCommentItem
from app.models.external import ProductCommentsResponse, CommentResponse
from app.core.database import db_connection, mongo_check
from app.core.logger import logger
from app.core.utils import validate_url, parse_date_to_ts, clean_text

class BrainAPI:
    def __init__(self):
        self.default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://brain.com.ua/"
        }
        self.default_api_url = "https://brain.com.ua/api/v1/product_comments/"
        self.default_timeout = aiohttp.ClientTimeout(total=10)
        self.default_retries = 3
        self.default_delay = 0.3
        
        self.months = {
            "січня": 1, "лютого": 2, "березня": 3, "квітня": 4,
            "травня": 5, "червня": 6, "липня": 7, "серпня": 8,
            "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12
        }
    
    # Extract product ID from URL
    def extract_product_id(self, url: str) -> str | None:
        match = re.search(r'-p(\d+)\.html', url)
        if match:
            product_id = match.group(1)
            logger.info("🟢 [BrainAPI][extract_product_id]: Found product ID: %s", product_id)
            return product_id
        
        logger.warning("🟡 [BrainAPI][extract_product_id]: Product ID not found in URL: %s", url)
        return None
    
    # Parse Ukrainian date string to timestamp
    def parse_date(self, date_str: str) -> int | None:
        try:
            parts = date_str.strip().split()
            if len(parts) != 3:
                return None
            
            day = int(parts[0])
            month = self.months.get(parts[1].lower())
            year = int(parts[2])
            
            if not month:
                logger.warning("🟡 [BrainAPI][parse_date]: Unknown month: %s", parts[1])
                return None
            
            dt = datetime(year, month, day)
            return int(dt.timestamp())
        except Exception as e:
            logger.warning("🟡 [BrainAPI][parse_date]: Failed to parse date '%s': %s", date_str, e)
            return None
    
    # Get reviews HTML from API
    async def get_reviews_html(self, session: aiohttp.ClientSession, product_id: str) -> str:
        logger.info("⚪ [BrainAPI][get_reviews_html]: Fetching reviews HTML for product %s", product_id)

        api_url = f"{self.default_api_url}{product_id}"
        
        for attempt in range(1, self.default_retries + 1):
            try:
                async with session.get(api_url) as response:
                    response.raise_for_status()
                    data = await response.json()
                    html = data.get("commentsTpl", "")
                    logger.info("🟢 [BrainAPI][get_reviews_html]: Fetched reviews HTML for product %s", product_id)
                    return html
            except Exception as e:
                logger.error("🔴 [BrainAPI][get_reviews_html]: Failed to fetch reviews, error: %s, attempt %s/%s", e, attempt, self.default_retries)
            
            await asyncio.sleep(self.default_delay * attempt)
        
        return ""

class BrainParser:
    def __init__(self):
        self.api = BrainAPI()
    
    # Save comments to MongoDB
    async def save_comments_to_db(self, url: str, comments: dict[str, BrainCommentItem]) -> None:
        product_doc = await db_connection.db.reviews.find_one({"url": url})
        current_comments = product_doc.get("comments", {}) if product_doc else {}

        new_comments_dict = {comment_id: comment.model_dump(mode="json") for comment_id, comment in comments.items()}
        current_comments.update(new_comments_dict)

        await db_connection.db.reviews.update_one(
            {"url": url},
            {"$set": {"comments": current_comments}},
            upsert=True
        )
    
    async def parse(self, url: str, **kwargs) -> BrainProductData:
        logger.info("⚪ [BrainParser][parse]: Parsing Brain URL: %s", url)

        url, path, slug = validate_url(url, domain="brain.com.ua")
        if not url or not path or not slug:
            logger.error("🔴 [BrainParser][parse]: Could not validate URL: %s", url)
            return BrainProductData(url=url, comments={})

        date_to_str = kwargs.get("date_to")
        date_to_ts = parse_date_to_ts(date_to_str)

        product_id = self.api.extract_product_id(url)
        if not product_id:
            logger.error("🔴 [BrainParser][parse]: Could not extract product ID from URL: %s", url)
            return BrainProductData(url=url, comments={})
        
        brain_comments = {}
        
        async def parse_comment(comment_item, comment_index: int) -> tuple[str, BrainCommentItem | None]:
            # data-cid=comment_id
            comment_id = comment_item["data-cid"]
            
            # Date
            date_tag = comment_item.find("div", class_="br-pt-bc-date")
            if not date_tag:
                return None, None
            
            date_str = date_tag.text.strip()
            created_at_ts = self.api.parse_date(date_str)
            if not created_at_ts:
                return None, None
            
            # Check date filter
            if date_to_ts and created_at_ts > date_to_ts:
                return None, None
            
            # Text
            text_tag = comment_item.find("div", class_="br-comment-text")
            text = clean_text(text_tag.text.strip()) if text_tag else ""
            
            # Rating
            rating_tag = comment_item.find("div", class_="br-pt-bc-rating")
            rating = float(rating_tag["data-comment-mark"]) if rating_tag and rating_tag.has_attr("data-comment-mark") else 0.0
                        
            comment_obj = BrainCommentItem(
                rating=rating,
                advantages="",
                shortcomings="",
                comment=text,
                created_at=created_at_ts,
                parsed_at=int(datetime.now(timezone.utc).timestamp())
            )
            
            return comment_id, comment_obj

        async with aiohttp.ClientSession(headers=self.api.default_headers, timeout=self.api.default_timeout) as session:
            html = await self.api.get_reviews_html(session, product_id)
            
            if not html:
                logger.warning("🟡 [BrainParser][parse]: No HTML received for product %s", product_id)
                return BrainProductData(url=url, comments={})
            
            soup = BeautifulSoup(html, "html.parser")
            reviews_findall = soup.find_all("div", class_="br-pt-bc-item br-ct-bc-item-out br-pt-bc-item-in deep-1")
            
            logger.info("🟢 [BrainParser][parse]: Found %s reviews", len(reviews_findall))
            
            for index, comment_item in enumerate(reviews_findall):
                comment_id, comment_obj = await parse_comment(comment_item, index)
                if comment_id and comment_obj:
                    brain_comments[comment_id] = comment_obj
        
        logger.info("🟢 [BrainParser][parse]: Parsed %s reviews for %s.", len(brain_comments), url)
        
        mongo_ok = await mongo_check()
        if mongo_ok:
            await self.save_comments_to_db(url, brain_comments)
            logger.info("🟢 [BrainParser][parse]: Saved %s reviews for %s.", len(brain_comments), url)
        else:
            logger.warning("🟡 [BrainParser][parse]: MongoDB connection not established, skipping saving reviews for %s.", url)
        
        return BrainProductData(url=url, comments=brain_comments)
    
    # Convert internal model to external API response model
    def to_external(self, internal_data: BrainProductData):
        return ProductCommentsResponse(
            url=internal_data.url,
            comments=[
                CommentResponse(
                    rating=comment_data.rating,
                    advantages=comment_data.advantages,
                    shortcomings=comment_data.shortcomings,
                    comment=comment_data.comment
                ) for _, comment_data in internal_data.comments.items()
            ]
        )
