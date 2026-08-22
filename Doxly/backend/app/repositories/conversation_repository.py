import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Citation, Conversation, ConversationDocument, Message
from app.repositories.base import TenantScopedRepository


class ConversationRepository(TenantScopedRepository[Conversation]):
    model = Conversation


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
