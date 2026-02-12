from pydantic import BaseModel

# Hotline models
class OfferResponse(BaseModel):
    url: str
    original_url: str | None = None
    title: str = ""
    shop: str = ""
    price: float = 0.0
    is_used: bool = False

class ProductOffersResponse(BaseModel):
    url: str
    offers: list[OfferResponse]

# Comfy models
class CommentResponse(BaseModel):
    rating: float
    advantages: str = ""
    shortcomings: str = ""
    comment: str = ""

class ProductCommentsResponse(BaseModel):
    url: str
    comments: list[CommentResponse]
