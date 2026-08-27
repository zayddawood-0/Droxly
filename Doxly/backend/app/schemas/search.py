"""api.md §8 (/search) request/response shapes — tasks/remediation-plan.md R8."""

import uuid

from pydantic import BaseModel


class SearchHighlight(BaseModel):
    start: int
    end: int


class SearchSnippet(BaseModel):
    """
    api.md §8 — offsets into `text`, never pre-built HTML: `text` is a raw,
    untrusted excerpt of user-uploaded document content (`CLAUDE.md` §6,
    `security.md` §6.2), so the API never returns markup for a client to
    inject. The already-built frontend (`frontend/lib/api/search.ts`)
    wraps each `[start, end)` range in a real `<mark>` element itself.
    """

    text: str
    highlights: list[SearchHighlight]


class SearchResultItem(BaseModel):
    document_id: uuid.UUID
    file_name: str
    snippet: SearchSnippet
    relevance_score: float
    matched_page: int | None


class SearchResponse(BaseModel):
    items: list[SearchResultItem]
    total: int
    limit: int
    offset: int
