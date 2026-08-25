import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Citation, Conversation, ConversationDocument, Message
from app.repositories.base import TenantScopedRepository


class ConversationRepository(TenantScopedRepository[Conversation]):
    model = Conversation

    async def get(self, user_id: uuid.UUID, id: uuid.UUID) -> Conversation | None:
        """
        Overrides the generic base the same way DocumentRepository does
        (skills/backend.md §4): a soft-deleted conversation must 404 exactly
        like one owned by another user (api.md §4 DELETE's "soft-deletes" —
        it should disappear from every subsequent lookup immediately).
        """
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.id == id,
                Conversation.user_id == user_id,
                Conversation.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_paginated(
        self, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[Sequence[Conversation], int]:
        """api.md §4 GET /chat/conversations — "sorted by updated_at desc"."""
        base_filters = [
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        ]
        stmt = (
            select(Conversation)
            .where(*base_filters)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = select(func.count()).select_from(Conversation).where(*base_filters)
        items = (await self.session.execute(stmt)).scalars().all()
        total = (await self.session.execute(count_stmt)).scalar_one()
        return items, total

    async def soft_delete(
        self, user_id: uuid.UUID, id: uuid.UUID
    ) -> Conversation | None:
        """api.md §4 DELETE — soft-deletes (`deleted_at`), same pattern as
        DocumentRepository.soft_delete (R2)."""
        conversation = await self.get(user_id, id)
        if conversation is None:
            return None
        conversation.deleted_at = datetime.now(UTC)
        await self.session.flush()
        return conversation

    async def touch(self, conversation: Conversation) -> None:
        """
        Bumps `updated_at` so GET /chat/conversations' "sorted by updated_at
        desc" reflects the conversation's most recent activity. Inserting a
        child `messages` row does NOT itself mark the parent `Conversation`
        object dirty for SQLAlchemy's UpdatedAtMixin `onupdate` to fire, so
        this is called explicitly whenever a turn completes.
        """
        conversation.updated_at = datetime.now(UTC)
        await self.session.flush()


class ConversationDocumentRepository:
    """Join table — tenancy enforced transitively through the owning conversation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_document_ids(self, conversation_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self.session.execute(
            select(ConversationDocument.document_id).where(
                ConversationDocument.conversation_id == conversation_id
            )
        )
        return list(result.scalars().all())

    async def add(self, conversation_id: uuid.UUID, document_id: uuid.UUID) -> None:
        self.session.add(
            ConversationDocument(
                conversation_id=conversation_id, document_id=document_id
            )
        )
        await self.session.flush()


class MessageRepository(TenantScopedRepository[Message]):
    model = Message

    async def list_for_conversation(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[Message]:
        """api.md §4 GET .../{id} — "ordered oldest-first"."""
        result = await self.session.execute(
            select(Message)
            .where(
                Message.user_id == user_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_preceding_user_message(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID, before_created_at
    ) -> Message | None:
        """
        api.md §4 regenerate — "the preceding user message (found by walking
        back from message_id to the nearest prior role='user' message)".
        Ordered by created_at desc from at-or-before the assistant message
        being regenerated, so the first row is the nearest prior turn.

        Deliberately `<=`, not `<`: the user and assistant message of the
        *same* turn are both written inside one request's single
        transaction (`chat_service.py`'s prepare_message_turn +
        generate_turn_events), and Postgres's `now()` returns the
        transaction's start time, not per-statement wall-clock time — so a
        turn's own pair of rows can (and, for the very first exchange in a
        conversation, routinely does) share the exact same `created_at`. A
        strict `<` would then never find that turn's own user message,
        breaking regenerate on the single most common case. The `role`
        filter alone already excludes the assistant row itself from ever
        matching, so `<=` introduces no risk of "finding" the message being
        regenerated.
        """
        result = await self.session.execute(
            select(Message)
            .where(
                Message.user_id == user_id,
                Message.conversation_id == conversation_id,
                Message.role == "user",
                Message.created_at <= before_created_at,
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


class CitationRepository:
    """
    specs/database.md §3.10 — citations has no user_id column at all;
    tenancy is enforced transitively through its parent message (whose
    conversation the caller must already own). Not a TenantScopedRepository
    subclass since the generic base's user_id-column assumption doesn't fit.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_message(self, message_id: uuid.UUID) -> list[Citation]:
        result = await self.session.execute(
            select(Citation).where(Citation.message_id == message_id)
        )
        return list(result.scalars().all())

    async def create(self, **fields) -> Citation:
        citation = Citation(**fields)
        self.session.add(citation)
        await self.session.flush()
        return citation
