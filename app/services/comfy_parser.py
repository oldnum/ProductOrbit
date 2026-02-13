import aiohttp
import asyncio
import re
from datetime import datetime, timezone
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from app.models.internal import ComfyProductData, ComfyCommentItem
from app.models.external import ProductCommentsResponse, CommentResponse
from app.core.database import db_connection, mongo_check
from app.core.logger import logger
from app.core.utils import validate_url, parse_date_to_ts, clean_text, get_headers

class ComfyAPI:
    def __init__(self):
        self.default_headers = {
            "Referer": "https://comfy.ua/",
            "Cookie": "g_state={}"
        }
        self.default_api_url = "https://im.comfy.ua/api/reviews/paged"
        self.default_timeout = aiohttp.ClientTimeout(total=10)
        self.default_timeout_playwright = 5
        self.default_retries = 3
        self.default_delay = 0.3
    
    # Get page content
    async def get_page_content(self, url: str) -> str:
        logger.info("⚪ [ComfyAPI][get_page_content]: Fetching page %s", url)

        for attempt in range(1, self.default_retries + 1):
            try:
                headers = get_headers(self.default_headers)

                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        headless=True, 
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                            "--disable-infobars",
                            "--disable-extensions"
                        ], 
                        slow_mo=0
                    )

                    context = await browser.new_context(
                        user_agent=headers["User-Agent"],
                        extra_http_headers=headers,
                        viewport={"width": 1920, "height": 1080},
                        locale="uk-UA"
                    )

                    page = await context.new_page()
                    stealth = Stealth()
                    await stealth.apply_stealth_async(page)

                    await page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "font", "media", "stylesheet"] else r.continue_())
                    await page.goto(url, wait_until="domcontentloaded", timeout=self.default_timeout_playwright * 1000)

                    html = await page.content()
                    if "Pardon Our Interruption" in html:
                        raise Exception("Page is blocked by Cloudflare")

                    logger.info("🟢 [ComfyAPI][get_page_content]: Fetched page %s", url)
                    return html

            except Exception as e:
                logger.error("🔴 [ComfyAPI][get_page_content]: Failed to fetch page %s: %s, attempt %s", url, e, attempt)
            
            await asyncio.sleep(self.default_delay * attempt)
        
        return ""

    # Get product info from page content
    async def get_product_info(self, url: str):
        content = await self.get_page_content(url)
        if not content:
            return None, None, None
        
        product_id, storeId, reviews_total = None, None, None

        match_id = re.search(r'"product":\s*{\s*"id":\s*(\d+)', content)
        if match_id:
            product_id = match_id.group(1)
            logger.info("🟢 [ComfyAPI][get_product_info]: Found product ID: %s", product_id)
        else:
            logger.warning("🟡 [ComfyAPI][get_product_info]: Product ID not found.")

        match_storeId = re.search(r'"storeId":\s*"(\d+)"', content) # "storeId": "5",
        if match_storeId:
            storeId = match_storeId.group(1)
            logger.info("🟢 [ComfyAPI][get_product_info]: Found storeId: %s", storeId)
        else:
            logger.warning("🟡 [ComfyAPI][get_product_info]: StoreId not found.")

        match_total = re.search(r'"reviewsTotal":\s*(\d+)', content) # "reviewsTotal": 90
        if match_total:
            reviews_total = int(match_total.group(1))
            logger.info("🟢 [ComfyAPI][get_product_info]: Found reviews total: %s", reviews_total)
        else:
            logger.warning("🟡 [ComfyAPI][get_product_info]: Reviews total not found.")
        
        return storeId, product_id, reviews_total

    # Get reviews from API
    async def get_reviews(self, session: aiohttp.ClientSession, product_id: str, storeId: str, page: int = 1, pageSize: int = 1) -> list:
        params = {
            "productId": product_id,
            "storeId": storeId,
            "page": page,
            "pageSize": pageSize,
            "type": "1",
            "order": "date",
            "parseCodes": "1"
        }
        
        for attempt in range(1, self.default_retries + 1):
            try:
                async with session.get(self.default_api_url, params=params) as response:
                    response.raise_for_status()
                    logger.info("🟢 [ComfyAPI][get_reviews]: Fetched reviews page %s", page)
                    data = await response.json()
                    return data.get("reviews", [])
            except Exception as e:
                logger.error("🔴 [ComfyAPI][get_reviews]: Failed to fetch reviews page %s, error: %s, attempt %s", page, e, attempt)

            await asyncio.sleep(self.default_delay * attempt)
        
        return []

class ComfyParser:
    def __init__(self):
        self.api = ComfyAPI()

    # Save comments to database
    async def save_comments_to_db(self, url: str, comments: dict[str, ComfyCommentItem]) -> None:
        product_doc = await db_connection.db.reviews.find_one({"url": url})
        current_comments = product_doc.get("comments", {}) if product_doc else {}

        new_comments_dict = {comment_id: comment.model_dump(mode="json") for comment_id, comment in comments.items()}
        current_comments.update(new_comments_dict)

        await db_connection.db.reviews.update_one(
            {"url": url},
            {"$set": {"comments": current_comments}},
            upsert=True
        )
    
    # Main parsing function
    async def parse(self, url: str, **kwargs) -> ComfyProductData:
        logger.info("⚪ [ComfyParser][parse]: Parsing Comfy URL: %s", url)

        url, path, slug = validate_url(url, domain="comfy.ua")
        if not url or not path or not slug:
            logger.error("🔴 [ComfyParser][parse]: Could not validate URL: %s", url)
            return ComfyProductData(url=url, comments={})

        date_to_str = kwargs.get("date_to")
        date_to_ts = parse_date_to_ts(date_to_str)

        storeId, product_id, reviews_total = await self.api.get_product_info(url)
        if not storeId or not product_id or not reviews_total:
            logger.error("🔴 [ComfyParser][parse]: Could not extract storeId, product ID or reviews total for %s", url)
            return ComfyProductData(url=url, comments={})

        comfy_comments = {}
        page_size = int(reviews_total // 10)
        if page_size == 0: page_size = 1

        logger.info("🟢 [ComfyParser][parse]: Total reviews: %s, Total pages: %s", reviews_total, page_size)
        
        # Parse review from raw data
        async def parse_review(review: dict) -> tuple[str, ComfyCommentItem]:
            created_at_str = review.get("createdAt")
            if not created_at_str:
                return None, None

            try:
                created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
                created_at_ts = int(created_at.timestamp())
            except ValueError:
                logger.warning("🟡 [ComfyParser][parse]: Failed to parse date %s", created_at_str)
                return None, None

            if date_to_ts and created_at_ts > date_to_ts:
                return None, None
            
            review_id = review.get("reviewId")
            return review_id, ComfyCommentItem(
                rating=float(review.get("productRating", 0)) / 20.0 if review.get("productRating") else 0.0,  # 100 -> 5.0
                advantages=clean_text(review.get("advantages")),
                shortcomings=clean_text(review.get("disadvantages")),
                comment=clean_text(review.get("detail")),
                created_at=created_at_ts,
                parsed_at=int(datetime.now(timezone.utc).timestamp())
            )

        async with aiohttp.ClientSession(headers=get_headers(self.api.default_headers), timeout=self.api.default_timeout) as session:
            for page in range(1, page_size + 1):
                raw_reviews = await self.api.get_reviews(
                    session=session,
                    product_id=product_id,
                    storeId=storeId,
                    page=page,
                    pageSize=page_size
                )
                
                if not raw_reviews:
                    logger.warning("🟣 [ComfyParser][parse]: No reviews on page %s.", page)
                    continue

                for review in raw_reviews:
                    review_id, comment_item = await parse_review(review)
                    if review_id and comment_item:
                        comfy_comments[review_id] = comment_item
        
        logger.info("🟢 [ComfyParser][parse]: Parsed %s reviews for %s.", len(comfy_comments), url)
        
        mongo_ok = await mongo_check()
        if mongo_ok:
            await self.save_comments_to_db(url, comfy_comments)
            logger.info("🟢 [ComfyParser][parse]: Saved %s reviews for %s.", len(comfy_comments), url)
        else:
            logger.warning("🟡 [ComfyParser][parse]: MongoDB connection not established, skipping saving reviews for %s.", url)
        
        return ComfyProductData(url=url, comments=comfy_comments)
    
    # Convert internal data to external format
    def to_external(self, internal_data: ComfyProductData):
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