"""
Common reusable models for API endpoints
"""
from typing import Annotated

from fastapi import Query


def pagination_params(
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of items to return")] = 50,
    offset: Annotated[int, Query(ge=0, description="Number of items to skip")] = 0
) -> dict:
    """Reusable pagination parameters"""
    return {"limit": limit, "offset": offset}


def ordering_params(
    order: Annotated[str, Query(pattern="^(asc|desc)$", description="Sort order")] = "desc"
) -> dict:
    """Reusable ordering parameters"""
    return {"order": order}


PaginationDep = Annotated[dict, Query()]
