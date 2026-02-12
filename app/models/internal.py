from pydantic import BaseModel, Field
from datetime import datetime

# Hotline models
class HotlineOfferItem(BaseModel):
    url: str
    original_url: str | None = None
    title: str = ""
    shop: str = ""
    price: float = 0.0
    is_used: bool = False
    parsed_at: int

class HotlineProductData(BaseModel):
    url: str
    offers: dict[str, HotlineOfferItem]

# Comfy models
class ComfyCommentItem(BaseModel):
    rating: float = 0.0
    advantages: str = ""
    shortcomings: str = ""
    comment: str = ""
    created_at: int
    parsed_at: int

class ComfyProductData(BaseModel):
    url: str
    comments: dict[str, ComfyCommentItem]

# Brain models
class BrainCommentItem(BaseModel):
    rating: float = 0.0
    advantages: str = ""
    shortcomings: str = ""
    comment: str = ""
    created_at: int
    parsed_at: int

class BrainProductData(BaseModel):
    url: str
    comments: dict[str, BrainCommentItem]
