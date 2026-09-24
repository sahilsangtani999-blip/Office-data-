"""
API Router for Natural-Language Search & Query Engine.
Phase 2.2 — RSSB Office Data Platform.

Provides:
- POST /api/v1/query: Submit natural language query and retrieve structured search results.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.search import QueryRequest, SearchResult
from app.services.query_planner import DeterministicQueryPlanner
from app.services.search_service import SearchContext, SearchService

router = APIRouter(prefix="/api/v1", tags=["Search & Query Engine"])


def get_search_context(
    x_user_id: Optional[str] = Header(default="dev-user"),
    x_user_role: Optional[str] = Header(default="user"),
    x_authorized: Optional[str] = Header(default="true"),
) -> SearchContext:
    """Dependency preparing for future authorization headers."""
    is_auth = str(x_authorized).lower() in ("true", "1", "yes")
    return SearchContext(
        user_id=x_user_id or "dev-user",
        roles=[x_user_role or "user"],
        is_authorized=is_auth,
    )


@router.post(
    "/query",
    response_model=SearchResult,
    status_code=status.HTTP_200_OK,
    summary="Natural Language Search Query",
    description="Processes a natural language query through deterministic parsing, queries PostgreSQL, and returns structured calculations, records, and provenance.",
)
def process_query(
    payload: QueryRequest,
    db: Session = Depends(get_db),
    context: SearchContext = Depends(get_search_context),
) -> SearchResult:
    """
    Query execution endpoint:
    1. Deterministic query planner creates a structured QueryPlan.
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

    planner = DeterministicQueryPlanner()
    plan_result = planner.plan(payload.question)

    search_service = SearchService(db=db, context=context)
    result = search_service.execute_search(plan_result, payload.question)

    return result
