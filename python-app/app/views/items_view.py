"""
View layer: Pydantic schemas define the response "shape" (FastAPI's
equivalent of a view/serializer) and are also what powers the Swagger UI
docs at /docs - interns can see exact response shapes without reading code.
"""
from typing import List

from pydantic import BaseModel


class Item(BaseModel):
    id: str
    name: str
    createdAt: str


class CreateItemRequest(BaseModel):
    name: str = "unnamed-item"


class ItemsOverview(BaseModel):
    items: List[Item]
    count: int
    computedAt: str


class HealthStatus(BaseModel):
    status: str
