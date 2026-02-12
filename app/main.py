# SIGNATURE: OLDNUM

import sys
import logging
import uvicorn
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from app.core.database import db_connection, mongo_connect, mongo_disconnect, mongo_check
from app.services.hotline_parser import HotlineParser
from app.services.parser_service import ParserFactory
from app.core.logger import logger
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("⚪ [Main]: Application startup, connecting to MongoDB...")
    try:
        await mongo_connect()
        if db_connection.db is None:
            raise RuntimeError("Database connection object is None after connect.")
        logger.info("🟢 [Main]: Connected to MongoDB successfully.")
    except Exception as e:
        logger.critical("🔴 [Main]: Failed to connect to MongoDB: %s. Exiting.", e)
        sys.exit(1)

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("⚪ [Main]: Application shutdown, disconnecting from MongoDB...")
    await mongo_disconnect()
    logger.info("🟢 [Main]: Disconnected from MongoDB.")

# API endpoint /product/offers
@app.get("/product/offers")
async def get_product_offers(
    url: str = Query(..., description="URL of the product on Hotline"),
    timeout_limit: int | None = Query(None, description="Timeout limit in seconds. Maximum is 60, minimum is 10, default is 60."),
    count_limit: int | None = Query(None, description="Limit number of offers. Maximum is 1000, minimum is 10, default is 10."),
    sort: str | None = Query(None, description="Sort order: 'asc' or 'desc'. Default is None (skip sort)."),
):
    logger.info("⚪ [API]: Received request for %s", url)
    
    try:
        parser = ParserFactory.get_parser(url)
        internal_data = await parser.parse(
            url, 
            timeout_limit=timeout_limit, 
            count_limit=count_limit, 
            price_sort=sort
        )

        external_data = parser.to_external(internal_data)
        return JSONResponse(status_code=200, content=external_data.model_dump(mode="json"))
    
    except Exception as e:
        logger.error("🔴 [API]: Error processing request: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})

# API endpoint /product/comments
@app.get("/product/comments")
async def get_product_comments(
    url: str = Query(..., description="URL of the product (Comfy or Brain)"),
    date_to: Optional[str] = Query(None, description="Filter reviews up to date (YYYY-MM-DD)")
):
    logger.info("⚪ [API]: Received comments request for %s", url)
    
    try:
        parser = ParserFactory.get_parser(url)
        internal_data = await parser.parse(url, date_to=date_to)

        external_data = parser.to_external(internal_data)
        return JSONResponse(status_code=200, content=external_data.model_dump(mode="json"))

    except Exception as e:
        logger.error("🔴 [API]: Error processing comments request: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})