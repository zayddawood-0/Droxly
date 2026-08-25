"""api.md §4 (/chat) — tasks/remediation-plan.md R4."""

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import EmbeddingProvider, get_embedding_provider
from app.ai.llm import LLMProvider, get_llm_provider
from app.core.csrf import verify_csrf
from app.core.dependencies import get_current_user, get_db_session
from app.core.rate_limit import rate_limit_ai, rate_limit_general
from app.core.security import AccessTokenClaims
from app.models import Conversation, Message
from app.repositories.conversation_repository import (
    CitationRepository,
    ConversationDocumentRepository,
    ConversationRepository,
    MessageRepository,
)
from app.repositories.document_repository import (
    DocumentChunkRepository,
    DocumentRepository,
)
from app.repositories.observability_repository import AiRequestRepository
from app.schemas.chat import (
    ChatMessageRequest,
    CitationResponse,
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationDetailResponse,
    ConversationListItem,
    ConversationListResponse,
    MessageResponse,
    StopResponse,
)
from app.services.chat_service import ChatService
from app.services.retrieval_service import RetrievalService

router = APIRouter(
    prefix="/chat", tags=["chat"], dependencies=[Depends(rate_limit_general)]
)


def get_chat_service(
    db: AsyncSession = Depends(get_db_session),
    llm_provider: LLMProvider = Depends(get_llm_provider),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
) -> ChatService:
    document_repo = DocumentRepository(db)
    retrieval_service = RetrievalService(
        DocumentChunkRepository(db), document_repo, embedding_provider
    )
    return ChatService(
        ConversationRepository(db),
        ConversationDocumentRepository(db),
        MessageRepository(db),
        CitationRepository(db),
        document_repo,
        AiRequestRepository(db),
        retrieval_service,
        llm_provider,
    )


def _to_list_item(
    conversation: Conversation, document_ids: list[uuid.UUID]
) -> ConversationListItem:
    return ConversationListItem(
        id=conversation.id,
        title=conversation.title,
        scope_type=conversation.scope_type,  # type: ignore[arg-type]
        document_ids=document_ids,
        updated_at=conversation.updated_at,
    )


def _to_message_response(message: Message, citations: list) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        role=message.role,  # type: ignore[arg-type]
        content=message.content,
        citations=[
            CitationResponse(
                document_id=c.document_id,
                page_number=c.page_number,
                snippet=c.snippet,
                relevance_score=c.relevance_score,
            )
            for c in citations
        ],
        created_at=message.created_at,
    )


@router.post(
    "/conversations",
    response_model=ConversationCreateResponse,
    status_code=201,
    dependencies=[Depends(verify_csrf)],
)
async def create_conversation(
    body: ConversationCreateRequest,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
) -> ConversationCreateResponse:
    conversation = await service.create_conversation(
        current_user.user_id, body.document_ids
    )
    return ConversationCreateResponse(
        id=conversation.id,
        scope_type=conversation.scope_type,  # type: ignore[arg-type]
        document_ids=body.document_ids,
        title=None,
        created_at=conversation.created_at,
    )


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
) -> ConversationListResponse:
    conversations, document_ids_by_conversation, total = (
        await service.list_conversations(
            current_user.user_id, limit=limit, offset=offset
        )
    )
    items = [
        _to_list_item(c, document_ids_by_conversation.get(c.id, []))
        for c in conversations
    ]
    return ConversationListResponse(
        items=items, total=total, limit=limit, offset=offset
    )


@router.get(
    "/conversations/{conversation_id}", response_model=ConversationDetailResponse
)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
) -> ConversationDetailResponse:
    conversation, document_ids, messages, citations_by_message = (
        await service.get_conversation_detail(current_user.user_id, conversation_id)
    )
    base = _to_list_item(conversation, document_ids)
    return ConversationDetailResponse(
        **base.model_dump(),
        created_at=conversation.created_at,
        messages=[
            _to_message_response(m, citations_by_message.get(m.id, []))
            for m in messages
        ],
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=204,
    dependencies=[Depends(verify_csrf)],
)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
) -> None:
    await service.delete_conversation(current_user.user_id, conversation_id)


@router.post(
    "/conversations/{conversation_id}/messages",
    dependencies=[Depends(verify_csrf), Depends(rate_limit_ai)],
)
async def send_message(
    conversation_id: uuid.UUID,
    body: ChatMessageRequest,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    conversation, user_message, document_ids = await service.prepare_message_turn(
        current_user.user_id, conversation_id, body.content
    )
    return StreamingResponse(
        service.generate_turn_events(
            current_user.user_id, conversation, user_message, document_ids
        ),
        media_type="text/event-stream",
    )


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/stop",
    response_model=StopResponse,
    dependencies=[Depends(verify_csrf)],
)
async def stop_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
) -> StopResponse:
    await service.stop_message(current_user.user_id, conversation_id, message_id)
    return StopResponse(message_id=message_id, status="stopped")


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/regenerate",
    dependencies=[Depends(verify_csrf), Depends(rate_limit_ai)],
)
async def regenerate_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    conversation, user_message, document_ids = await service.prepare_regenerate_turn(
        current_user.user_id, conversation_id, message_id
    )
    return StreamingResponse(
        service.generate_turn_events(
            current_user.user_id, conversation, user_message, document_ids
        ),
        media_type="text/event-stream",
    )
