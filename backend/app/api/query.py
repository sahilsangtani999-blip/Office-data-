"""
API Router for Natural-Language Search & Query Engine.
Phase 2.2 — RSSB Office Data Platform.

Provides:
- POST /api/v1/query: Submit natural language query and retrieve structured search results.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import AuthenticatedUserContext, get_current_user
from app.database import get_db
from app.schemas.search import QueryRequest, SearchResult
from app.services.query_planner import QueryPlanner, get_query_planner
from app.services.search_service import SearchContext, SearchService

router = APIRouter(prefix="/api/v1", tags=["Search & Query Engine"])


def get_search_context(
    user: AuthenticatedUserContext = Depends(get_current_user),
) -> SearchContext:
    """Dependency resolving SearchContext from the authenticated user and checking read permissions."""
    is_authorized = user.is_authenticated and user.has_permission("read")
    return SearchContext(
        user_id=user.username or user.user_id,
        roles=user.roles,
        is_authorized=is_authorized,
    )


@router.post(
    "/query",
    response_model=SearchResult,
    status_code=status.HTTP_200_OK,
    summary="Natural Language Search Query",
    description="Processes a natural language query through deterministic parsing or optional AI planner, queries PostgreSQL, and returns structured calculations, records, and provenance.",
)
def process_query(
    payload: QueryRequest,
    db: Session = Depends(get_db),
    context: SearchContext = Depends(get_search_context),
) -> SearchResult:
    """
    Query execution endpoint:
    1. QueryPlanner interface (Local or Optional AI) creates a structured QueryPlan.
    2. Search service verifies permissions and runs parameterized ORM retrieval.
    3. Numerical calculations are performed on actual DB values.
    4. Granular source references and machine-readable result returned.
    """
    if not payload.question or not payload.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question field must not be empty.",
        )

    try:
        context.verify_permission("read")
    except PermissionError as pe:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(pe),
        )

    planner: QueryPlanner = get_query_planner()
    search_service = SearchService(db=db, context=context, planner=planner)
    return search_service.search(payload.question)
