import aiohttp
import asyncio
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, urljoin
from itertools import islice

from app.models.internal import HotlineProductData, HotlineOfferItem
from app.models.external import ProductOffersResponse, OfferResponse
from app.core.database import db_connection, mongo_check
from app.core.logger import logger
from app.core.utils import validate_url, parse_date_to_ts, get_headers

class HotlineAPI:
    def __init__(self):
        self.default_headers = {
            "Referer": "https://hotline.ua/"
        }
        self.default_graphql_url = "https://hotline.ua/svc/frontend-api/graphql"
        self.default_timeout = aiohttp.ClientTimeout(total=10)
        self.default_retries = 3
        self.default_delay = 0.3

    def validate_query_params(self, timeout_limit: int | None, price_sort: str | None, count_limit: int):
        # Timeout limit validation
        if timeout_limit is None:
            timeout_limit = 60
        elif timeout_limit.is_integer():
            if timeout_limit > 60:
                timeout_limit = 60
            elif timeout_limit < 1:
                timeout_limit = 10
        else:
            logger.warning("🟡 [HotlineAPI][validate_query_params]: Timeout limit must be an integer, setting to 60.")
            timeout_limit = 60
        
        # Price sort validation
        if price_sort and price_sort not in ["asc", "desc"]:
            logger.warning("🟡 [HotlineAPI][validate_query_params]: Price sort must be 'asc' or 'desc', setting to None.")
            price_sort = None
        
        # Count limit validation
        if count_limit is None:
            count_limit = 10
        elif count_limit.is_integer():
            if count_limit > 1000:
                count_limit = 1000
            elif count_limit < 1:
                count_limit = 10
        else:
            logger.warning("🟡 [HotlineAPI][validate_query_params]: Count limit must be an integer, setting to 10.")
            count_limit = 10
        
        logger.info("🟢 [HotlineAPI][validate_query_params]: Timeout limit: %s, Price sort: %s, Count limit: %s.", timeout_limit, price_sort, count_limit)
        return timeout_limit, price_sort, count_limit
    
    # Get redirect URL
    async def get_redirect_url(self, session: aiohttp.ClientSession, url: str):
        logger.info("⚪ [HotlineAPI][get_redirect_url]: Getting redirect URL for: %s.", url)

        for attempt in range(1, self.default_retries + 1):
            try:
                async with session.head(url, headers=get_headers(self.default_headers), allow_redirects=False) as r:
                    redirect_url = r.headers.get("Location")

                if not redirect_url or redirect_url == url:
                    async with session.get(url, headers=get_headers(self.default_headers), allow_redirects=True) as r:
                        redirect_url = str(r.url)

                if redirect_url and redirect_url != url:
                    logger.info("🟢 [HotlineAPI][get_redirect_url]: Redirect URL: %s.", redirect_url)
                    return redirect_url

            except Exception as e:
                logger.error("🔴 [HotlineAPI][get_redirect_url]: Request error: %s, attempt %s/%s.", e, attempt, self.default_retries)

            await asyncio.sleep(self.default_delay * attempt)

        logger.info("🟢 [HotlineAPI][get_redirect_url]: Redirect URL: None.")
        return None

    # Fetch page JSON
    async def fetch_page_json(self, url: str, additional_json: dict, additional_headers: dict = None):
        logger.info("⚪ [HotlineAPI][fetch_page_json]: Fetching page JSON for URL: %s.", url)

        headers = get_headers(self.default_headers)
        if additional_headers:
            headers.update(additional_headers)

        for attempt in range(1, self.default_retries + 1):
            try:
                async with aiohttp.ClientSession(headers=headers, timeout=self.default_timeout) as session:
                    async with session.post(url, json=additional_json) as response:
                        response.raise_for_status()
                        logger.info("🟢 [HotlineAPI][fetch_page_json]: Request successful.")
                        return await response.json()
            except Exception as e:
                logger.error("🔴 [HotlineAPI][fetch_page_json]: Request error: %s, attempt %s/%s.", e, attempt + 1, self.default_retries)
            
            await asyncio.sleep(self.default_delay * attempt)

        return None

    # Get product token
    async def get_product_token(self, path: str):
        logger.info("⚪ [HotlineAPI][get_product_token]: Getting product token for path: %s.", path)
        
        query = {
            "operationName": "urlTypeDefiner",
            "variables": {"path": path},
            "query": """
                query urlTypeDefiner($path: String!) {
                    urlTypeDefiner(path: $path) {
                        token
                    }
                }
            """
        }

        result = await self.fetch_page_json(self.default_graphql_url, query)

        if result:
            token = result.get("data", {}).get("urlTypeDefiner", {}).get("token")
            if token:
                logger.info("🟢 [HotlineAPI][get_product_token]: Token received.")
                return token
        
        logger.warning("🟡 [HotlineAPI][get_product_token]: No token received.")
        return None

    # Get offers
    async def get_offers(
        self, 
        url: str, 
        path: str,
        slug: str,
        timeout_limit: int | None = None,
        price_sort: str | None = None,
        count_limit: int = 10
    ):
        logger.info("⚪ [HotlineAPI][get_offers]: Starting to fetch offers for URL: %s.", url)

        start_time = datetime.now(timezone.utc).timestamp()
        token = await self.get_product_token(path)

        if not token:
            logger.warning("🟡 [HotlineAPI][get_offers]: No token received, cannot fetch offers.")
            return []

        extra_headers = {
            "x-token": token,
            "x-referer": url
        }

        query = {
            "operationName": "getOffers",
            "variables": {"path": slug, "first": count_limit, "cityId": 187},
            "query": 
                """
                    query getOffers($path: String!, $first: Int!, $cityId: Int!) {
                        byPathQueryProduct(path: $path, cityId: $cityId) {
                            offers(first: $first) {
                                edges {
                                    node {
                                        _id
                                        conversionUrl
                                        condition
                                        conditionId
                                        descriptionFull
                                        firmTitle
                                        price
                                    }
                                }
                            }
                        }
                    }
                """
        }

        result = await self.fetch_page_json(
            self.default_graphql_url,
            query,
            additional_headers=extra_headers
        )

        if not result:
            logger.warning("🟡 [HotlineAPI][get_offers]: No result from GraphQL.")
            return []

        offers_data = result.get("data", {}).get("byPathQueryProduct", {}).get("offers", {}).get("edges", [])

        async def parse_offer(session: aiohttp.ClientSession, node: dict):
            offer_id = node.get("_id", "unknown")
            conversion_url = node.get("conversionUrl", "")
            full_url = urljoin("https://hotline.ua", conversion_url).rstrip("/")
            original_url = await self.get_redirect_url(session, full_url)
            return offer_id, HotlineOfferItem( 
                url=full_url,
                original_url=original_url,
                title=node.get("descriptionFull") or "",
                shop=node.get("firmTitle") or "",
                price=node.get("price") or 0.0,
                is_used=node.get("conditionId") == 1,
                parsed_at=int(datetime.now(timezone.utc).timestamp())
            )

        parsed_offers = {}
        async with aiohttp.ClientSession(timeout=self.default_timeout) as session:
            for offer in offers_data:
                if timeout_limit:
                    elapsed = datetime.now(timezone.utc).timestamp() - start_time
                    if elapsed >= timeout_limit:
                        logger.warning("🟡 [HotlineAPI][get_offers]: Timeout limit (%s s) reached. Returning %s partial results.", timeout_limit, len(parsed_offers))
                        break
                
                offer_id, offer_data = await parse_offer(session, offer.get("node", {}))
                parsed_offers[offer_id] = offer_data
                
                if count_limit and not price_sort and len(parsed_offers) >= count_limit:
                    break

        if price_sort:
            reverse = price_sort.lower() == "desc"
            parsed_offers = dict(
                sorted(
                    parsed_offers.items(),
                    key=lambda x: x[1].price,
                    reverse=reverse
                )
            )
            logger.info("🟢 [HotlineAPI][get_offers]: Sorted results by price (%s).", price_sort)

        if count_limit:
            parsed_offers = dict(islice(parsed_offers.items(), count_limit))
            logger.info("🟢 [HotlineAPI][get_offers]: Applied count limit: %s.", count_limit)

        logger.info("🟢 [HotlineAPI][get_offers]: Found %s offers.", len(parsed_offers))
        return parsed_offers

class HotlineParser:
    def __init__(self):
        self.api = HotlineAPI()

    # Save offers to MongoDB
    async def save_offers_to_db(self, url: str, offers: dict[str, HotlineOfferItem]):
        product_doc = await db_connection.db.products.find_one({"url": url})
        current_offers = product_doc.get("offers", {}) if product_doc else {}

        new_offers_dict = {offer_id: offer.model_dump(mode="json") for offer_id, offer in offers.items()}
        current_offers.update(new_offers_dict)

        await db_connection.db.products.update_one(
            {"url": url},
            {"$set": {"offers": current_offers}},
            upsert=True
        )

    # Parse offers from URL
    async def parse(self, url: str, **kwargs) -> HotlineProductData:
        logger.info("⚪ [HotlineParser][parse]: Starting parsing for %s.", url)

        url, path, slug = validate_url(url, domain="hotline.ua")
        if not url or not path or not slug:
            logger.error("🔴 [HotlineParser][parse]: Failed to validate URL.")
            return HotlineProductData(url=url, offers={})

        mongo_ok = await mongo_check()

        timeout_limit, price_sort, count_limit = self.api.validate_query_params(
            kwargs.get("timeout_limit"),
            kwargs.get("price_sort"),
            kwargs.get("count_limit")
        )

        offers: dict[str, HotlineOfferItem] = await self.api.get_offers(
            url=url,
            path=path,
            slug=slug,
            timeout_limit=timeout_limit,
            price_sort=price_sort,
            count_limit=count_limit
        )
        logger.info("🟢 [HotlineParser][parse]: Parsed %s offers total.", len(offers))

        if mongo_ok:
            await self.save_offers_to_db(url, offers)
            logger.info("🟢 [HotlineParser][parse]: Saved %s offers.", len(offers))
        else:
            logger.warning("🟡 [HotlineParser][parse]: Mongo unavailable, skipping save.")

        return HotlineProductData(url=url, offers=offers)
    
    # Convert internal model to external API response model
    def to_external(self, internal_data: HotlineProductData) -> ProductOffersResponse:
        return ProductOffersResponse(
            url=internal_data.url,
            offers=[
                OfferResponse(
                    url=offer_data.url,
                    original_url=offer_data.original_url,
                    title=offer_data.title,
                    shop=offer_data.shop,
                    price=offer_data.price,
                    is_used=offer_data.is_used
                )
                for _, offer_data in internal_data.offers.items()
            ]
        )
