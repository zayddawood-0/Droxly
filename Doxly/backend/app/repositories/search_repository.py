import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Text, case, func, literal, null, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk, DocumentTag

# rag.md §12 — reciprocal rank fusion constant ("a small constant, e.g., 60").
RRF_K = 60
# How many top candidates each ranking method (vector, full-text) contributes
# to the fused result before RRF combines them — bounds the query's cost
# independent of corpus size, mirroring retrieval_service.py's own top-k caps.
CANDIDATE_POOL = 50
# rag.md §6's relevance-threshold rejection, reused here: without a floor,
# pgvector's k-nearest-neighbor search always returns *something* (the least
# dissimilar chunk in the corpus), which would otherwise let a genuinely
# irrelevant chunk leak into the fused ranking purely because nothing better
# existed to compare it against — same default retrieval_service.py uses.
VECTOR_MIN_SIMILARITY = 0.75


@dataclass(frozen=True)
class SearchHit:
    """One fused, ranked search result row — api.md §8's per-matching-chunk
    grain. `page_number` is `None` for a filename-only match (rag.md §12's
    "documents.file_name for filename matches" — there is no chunk/page to
    point to)."""

    document_id: uuid.UUID
    file_name: str
    content: str
    page_number: int | None
    relevance_score: float


class SearchRepository:
    """
    rag.md §12 (Hybrid Search) — global, corpus-wide search combining
    Postgres full-text (`tsvector`/GIN, both `document_chunks.content` and
    `documents.file_name`) with pgvector cosine-similarity, fused via
    reciprocal rank fusion. Deliberately not a `TenantScopedRepository`
    subclass (like `DocumentTagRepository`) — this query spans multiple
    tables via CTEs rather than being generic CRUD over one model.

    Built with SQLAlchemy Core throughout (skills/database.md §3: raw
    `text()` is reserved for cases the ORM genuinely can't express) —
    `DocumentChunk.embedding.cosine_distance(...)` is the same construct
    `DocumentChunkRepository.similarity_search` already uses, so the
    pgvector parameter binding/type-decoding is proven, not new.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(
        self,
        user_id: uuid.UUID,
        query: str,
        query_embedding: list[float],
        *,
        limit: int,
        offset: int,
        mime_type: str | None = None,
        tag_id: uuid.UUID | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[list[SearchHit], int]:
        """
        Every filter here is applied to `filtered_documents` first
        (`NFR-SEC-001`: `user_id` scoping and soft-delete exclusion happen
        before either ranking method ever runs, not as an afterthought on
        the fused result), then both the vector and full-text candidate
        sets are restricted to that same filtered set via a join —
        `FR-SEARCH-002`'s filters narrow the corpus searched, not just the
        results shown.
        """
        filtered_documents_stmt = select(
            Document.id.label("id"), Document.file_name.label("file_name")
        ).where(Document.user_id == user_id, Document.deleted_at.is_(None))
        if mime_type is not None:
            filtered_documents_stmt = filtered_documents_stmt.where(
                Document.mime_type == mime_type
            )
        if status is not None:
            filtered_documents_stmt = filtered_documents_stmt.where(
                Document.status == status
            )
        if date_from is not None:
            filtered_documents_stmt = filtered_documents_stmt.where(
                Document.created_at >= date_from
            )
        if date_to is not None:
            filtered_documents_stmt = filtered_documents_stmt.where(
                Document.created_at <= date_to
            )
        if tag_id is not None:
            filtered_documents_stmt = filtered_documents_stmt.join(
                DocumentTag, DocumentTag.document_id == Document.id
            ).where(DocumentTag.tag_id == tag_id)
        filtered_documents = filtered_documents_stmt.cte("filtered_documents")

        tsquery = func.plainto_tsquery("english", query)

        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        similarity = 1 - distance
        vector_candidates = (
            select(
                DocumentChunk.id.label("chunk_id"),
                DocumentChunk.document_id.label("document_id"),
                func.row_number().over(order_by=distance.asc()).label("rnk"),
            )
            .join(
                filtered_documents,
                filtered_documents.c.id == DocumentChunk.document_id,
            )
            .where(
                DocumentChunk.user_id == user_id,
                DocumentChunk.embedding.is_not(None),
                similarity >= VECTOR_MIN_SIMILARITY,
            )
            .order_by(distance.asc())
            .limit(CANDIDATE_POOL)
            .cte("vector_candidates")
        )

        chunk_fulltext = (
            select(
                DocumentChunk.id.cast(Text).label("match_key"),
                DocumentChunk.id.label("chunk_id"),
                DocumentChunk.document_id.label("document_id"),
                func.ts_rank(DocumentChunk.search_vector, tsquery).label("score"),
            )
            .join(
                filtered_documents,
                filtered_documents.c.id == DocumentChunk.document_id,
            )
            .where(
                DocumentChunk.user_id == user_id,
                DocumentChunk.search_vector.op("@@")(tsquery),
            )
        )
        filename_fulltext = (
            select(
                (literal("file:") + filtered_documents.c.id.cast(Text)).label(
                    "match_key"
                ),
                null().cast(UUID(as_uuid=True)).label("chunk_id"),
                filtered_documents.c.id.label("document_id"),
                func.ts_rank(Document.search_vector, tsquery).label("score"),
            )
            .select_from(Document)
            .join(filtered_documents, filtered_documents.c.id == Document.id)
            .where(Document.search_vector.op("@@")(tsquery))
        )
        fulltext_union = chunk_fulltext.union_all(filename_fulltext).subquery(
            "fulltext_candidates"
        )
        fulltext_ranked = (
            select(
                fulltext_union.c.match_key,
                fulltext_union.c.chunk_id,
                fulltext_union.c.document_id,
                func.row_number()
                .over(order_by=fulltext_union.c.score.desc())
                .label("rnk"),
            )
            .order_by(fulltext_union.c.score.desc())
            .limit(CANDIDATE_POOL)
            .cte("fulltext_ranked")
        )

        vector_chunk_id_text = vector_candidates.c.chunk_id.cast(Text)
        join_condition = vector_chunk_id_text == fulltext_ranked.c.match_key
        rrf_score = case(
            (
                vector_candidates.c.rnk.is_not(None),
                1.0 / (RRF_K + vector_candidates.c.rnk),
            ),
            else_=0.0,
        ) + case(
            (fulltext_ranked.c.rnk.is_not(None), 1.0 / (RRF_K + fulltext_ranked.c.rnk)),
            else_=0.0,
        )
        combined = (
            select(
                func.coalesce(
                    vector_candidates.c.chunk_id, fulltext_ranked.c.chunk_id
                ).label("chunk_id"),
                func.coalesce(vector_chunk_id_text, fulltext_ranked.c.match_key).label(
                    "match_key"
                ),
                func.coalesce(
                    vector_candidates.c.document_id, fulltext_ranked.c.document_id
                ).label("document_id"),
                rrf_score.label("relevance_score"),
            )
            .select_from(
                vector_candidates.join(
                    fulltext_ranked, join_condition, isouter=True, full=True
                )
            )
            .cte("combined")
        )

        final_content = func.coalesce(
            DocumentChunk.content, filtered_documents.c.file_name
        )
        final_stmt = (
            select(
                combined.c.document_id,
                filtered_documents.c.file_name,
                final_content.label("content"),
                DocumentChunk.page_number,
                combined.c.relevance_score,
            )
            .select_from(
                combined.join(
                    filtered_documents,
                    filtered_documents.c.id == combined.c.document_id,
                ).outerjoin(DocumentChunk, DocumentChunk.id == combined.c.chunk_id)
            )
            .order_by(combined.c.relevance_score.desc(), combined.c.match_key.asc())
        )

        count_stmt = select(func.count()).select_from(combined)
        total = (await self.session.execute(count_stmt)).scalar_one()

        rows = (
            await self.session.execute(final_stmt.limit(limit).offset(offset))
        ).all()
        hits = [
            SearchHit(
                document_id=row.document_id,
                file_name=row.file_name,
                content=row.content,
                page_number=row.page_number,
                relevance_score=float(row.relevance_score),
            )
            for row in rows
        ]
        return hits, total
