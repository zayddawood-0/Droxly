"""
tasks/remediation-plan.md R4 — FR-AI-001..006, FR-RAG-001..003 (consumed).

Composes the already-tested document_qa.py graph's own node functions
directly rather than invoking build_document_qa_graph(...).ainvoke() as one
opaque call (see tasks/R4-chat.md "Gap 3") — this lets the citation
validator's grounding check run on the *complete* answer before anything is
relayed to the SSE client (FR-AI-004's absolute "no fabricated citation"
guarantee), while still giving the client a progressive, chunked reveal
(FR-AI-005) and giving NFR-OBS-001 the provider's own real token/model
accounting (via `generate()`'s Completion, not an estimate).
"""

import json
import time
import uuid
from collections.abc import AsyncIterator, Sequence

from app.ai.graphs.document_qa import (
    NO_ANSWER_RESPONSE,
    OUT_OF_SCOPE_RESPONSE,
    QAState,
    answer_generator_node,
    citation_validator_node,
    classifier_node,
    retriever_node,
)
from app.ai.llm import LLMProvider
from app.ai.llm import Message as LLMMessage
from app.core import chat_stream_control as stream_control
from app.document_processing.chunking import count_tokens
from app.errors import DocumentNotReadyError, MessageNotInProgressError, NotFoundError
from app.models import Conversation, Message
from app.repositories.conversation_repository import (
    CitationRepository,
    ConversationDocumentRepository,
    ConversationRepository,
    MessageRepository,
)
from app.repositories.document_repository import DocumentRepository
from app.repositories.observability_repository import AiRequestRepository
from app.services.citation_service import CitationInput, CitationService
from app.services.retrieval_service import RetrievalService

# ai.md §6 — conversation history is bounded by a token budget, not an
# unbounded turn count (tasks/R4-chat.md's documented "hard truncation,
# not summarized" scope decision).
HISTORY_TOKEN_BUDGET = 2000

# database.md §3.7 "title ... auto-generated from first message"
# (tasks/R4-chat.md Gap 4 — a deterministic truncation, not a second LLM call).
TITLE_MAX_LENGTH = 60

_GENERATION_FAILED_MESSAGE = (
    "Something went wrong generating a response. Please try again."
)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class ChatService:
    def __init__(
        self,
        conversation_repo: ConversationRepository,
        conversation_document_repo: ConversationDocumentRepository,
        message_repo: MessageRepository,
        citation_repo: CitationRepository,
        document_repo: DocumentRepository,
        ai_request_repo: AiRequestRepository,
        retrieval_service: RetrievalService,
        llm_provider: LLMProvider,
    ) -> None:
        self.conversation_repo = conversation_repo
        self.conversation_document_repo = conversation_document_repo
        self.message_repo = message_repo
        self.citation_repo = citation_repo
        self.citation_service = CitationService(citation_repo)
        self.document_repo = document_repo
        self.ai_request_repo = ai_request_repo
        self.retrieval_service = retrieval_service
        self.llm_provider = llm_provider

    # --- FR-AI-001/002 — create ---

    async def create_conversation(
        self, user_id: uuid.UUID, document_ids: list[uuid.UUID]
    ) -> Conversation:
        if document_ids:
            await self._verify_documents_ready(user_id, document_ids)
            scope_type = (
                "single_document" if len(document_ids) == 1 else "multi_document"
            )
        else:
            scope_type = "workspace"

        conversation = await self.conversation_repo.create(
            user_id, scope_type=scope_type, title=None
        )
        for document_id in document_ids:
            await self.conversation_document_repo.add(conversation.id, document_id)
        return conversation

    # --- FR-AI-003 — list/detail/delete ---

    async def list_conversations(
        self, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[Sequence[Conversation], dict[uuid.UUID, list[uuid.UUID]], int]:
        conversations, total = await self.conversation_repo.list_paginated(
            user_id, limit=limit, offset=offset
        )
        document_ids_by_conversation = {
            c.id: await self.conversation_document_repo.list_document_ids(c.id)
            for c in conversations
        }
        return conversations, document_ids_by_conversation, total

    async def get_conversation_detail(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> tuple[Conversation, list[uuid.UUID], list[Message], dict[uuid.UUID, list]]:
        conversation = await self.conversation_repo.get(user_id, conversation_id)
        if conversation is None:
            raise NotFoundError()
        document_ids = await self.conversation_document_repo.list_document_ids(
            conversation.id
        )
        messages = await self.message_repo.list_for_conversation(
            user_id, conversation.id
        )
        citations_by_message = {
            message.id: await self.citation_repo.list_for_message(message.id)
            for message in messages
        }
        return conversation, document_ids, messages, citations_by_message

    async def delete_conversation(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> None:
        deleted = await self.conversation_repo.soft_delete(user_id, conversation_id)
        if deleted is None:
            raise NotFoundError()

    # --- turn preparation (runs BEFORE the SSE stream opens, per api.md:
    # errors are standard JSON pre-stream, never smuggled in as an event) ---

    async def prepare_message_turn(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID, content: str
    ) -> tuple[Conversation, Message, list[uuid.UUID]]:
        conversation = await self.conversation_repo.get(user_id, conversation_id)
        if conversation is None:
            raise NotFoundError()
        document_ids = await self.conversation_document_repo.list_document_ids(
            conversation.id
        )
        await self._verify_documents_ready(user_id, document_ids)

        user_message = await self.message_repo.create(
            user_id,
            conversation_id=conversation.id,
            role="user",
            content=content,
            token_count=count_tokens(content),
            status="complete",
        )
        if conversation.title is None:
            conversation.title = content[:TITLE_MAX_LENGTH]
        await self.conversation_repo.touch(conversation)
        return conversation, user_message, document_ids

    async def prepare_regenerate_turn(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID, message_id: uuid.UUID
    ) -> tuple[Conversation, Message, list[uuid.UUID]]:
        conversation = await self.conversation_repo.get(user_id, conversation_id)
        if conversation is None:
            raise NotFoundError()

        assistant_message = await self.message_repo.get(user_id, message_id)
        if (
            assistant_message is None
            or assistant_message.conversation_id != conversation.id
            or assistant_message.role != "assistant"
        ):
            raise NotFoundError()

        user_message = await self.message_repo.get_preceding_user_message(
            user_id, conversation.id, assistant_message.created_at
        )
        if user_message is None:
            raise NotFoundError()

        document_ids = await self.conversation_document_repo.list_document_ids(
            conversation.id
        )
        await self._verify_documents_ready(user_id, document_ids)
        return conversation, user_message, document_ids

    async def _verify_documents_ready(
        self, user_id: uuid.UUID, document_ids: list[uuid.UUID]
    ) -> None:
        if not document_ids:
            return
        documents = await self.document_repo.get_many(user_id, document_ids)
        if len(documents) != len(document_ids):
            raise NotFoundError()
        if any(document.status != "ready" for document in documents):
            raise DocumentNotReadyError()

    # --- FR-AI-006 — stop ---

    async def stop_message(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID, message_id: uuid.UUID
    ) -> None:
        message = await self.message_repo.get(user_id, message_id)
        if message is None or message.conversation_id != conversation_id:
            raise NotFoundError()
        stopped = await stream_control.request_stop(message_id)
        if not stopped:
            raise MessageNotInProgressError()

    # --- the streaming turn itself ---

    async def _assemble_history(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        before_created_at,
    ) -> list[LLMMessage]:
        all_messages = await self.message_repo.list_for_conversation(
            user_id, conversation_id
        )
        relevant = [
            m
            for m in all_messages
            if m.role in ("user", "assistant") and m.created_at < before_created_at
        ]
        budget = HISTORY_TOKEN_BUDGET
        selected: list[Message] = []
        for message in reversed(relevant):
            tokens = message.token_count or count_tokens(message.content)
            if selected and budget - tokens < 0:
                break
            selected.append(message)
            budget -= tokens
        selected.reverse()
        return [LLMMessage(role=m.role, content=m.content) for m in selected]  # type: ignore[arg-type]

    async def generate_turn_events(
        self,
        user_id: uuid.UUID,
        conversation: Conversation,
        user_message: Message,
        document_ids: list[uuid.UUID],
    ) -> AsyncIterator[str]:
        """
        The SSE body for both `POST .../messages` and `.../regenerate` —
        identical from this point on (api.md §4: regenerate's contract is
        "identical... except the initial message_id event echoes the
        existing user message's id", which the caller already resolved by
        the time this generator is invoked).
        """
        yield _sse("message_id", {"message_id": str(user_message.id)})

        await stream_control.mark_turn_started(user_message.id)
        start = time.monotonic()
        ai_status = "success"
        error_code: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        model_name = "n/a"
        # Tracks whatever text had actually been generated/relayed if a
        # later step (e.g. persisting citations) fails after generation
        # itself succeeded — so the persisted "incomplete" message isn't
        # falsely emptied when real content existed.
        partial_answer = ""

        try:
            history = await self._assemble_history(
                user_id, conversation.id, before_created_at=user_message.created_at
            )

            state: QAState = {
                "user_id": user_id,
                "conversation_id": conversation.id,
                "query": user_message.content,
                "history": history,  # type: ignore[typeddict-item]
            }

            classifier_result = await classifier_node(state, self.llm_provider)
            state.update(classifier_result)  # type: ignore[typeddict-item]
            classification_completion = classifier_result.get(
                "classification_completion"
            )
            if classification_completion is not None:
                input_tokens = classification_completion.input_tokens
                output_tokens = classification_completion.output_tokens
                model_name = classification_completion.model

            if state["intent"] == "out_of_scope":
                async for event in self._finalize_turn(
                    user_id, conversation, user_message, OUT_OF_SCOPE_RESPONSE, []
                ):
                    yield event
                return

            document_id = document_ids[0] if len(document_ids) == 1 else None
            retrieval_state: QAState = {
                **state,
                "document_id": document_id,
                "document_ids": document_ids if len(document_ids) > 1 else None,
            }
            retriever_result = await retriever_node(
                retrieval_state, self.retrieval_service
            )
            state.update(retriever_result)  # type: ignore[typeddict-item]

            if state["assembled_context"].is_empty:
                async for event in self._finalize_turn(
                    user_id, conversation, user_message, NO_ANSWER_RESPONSE, []
                ):
                    yield event
                return

            if await stream_control.is_stop_requested(user_message.id):
                await self._persist_stopped(user_id, conversation, user_message, "")
                return

            generation_result = await answer_generator_node(state, self.llm_provider)
            state.update(generation_result)  # type: ignore[typeddict-item]
            completion = generation_result.get("generation_completion")
            if completion is not None:
                input_tokens = completion.input_tokens
                output_tokens = completion.output_tokens
                model_name = completion.model

            # citation_validator_node mirrors LangGraph's own partial-update
            # merge semantics (its grounded-answer branch returns only
            # {"citations":..., "status":...}, relying on `draft_answer`
            # already being in state from answer_generator_node) — must be
            # merged into `state`, not read as a standalone return value.
            state.update(citation_validator_node(state))  # type: ignore[typeddict-item]
            final_answer = state["draft_answer"]
            partial_answer = final_answer
            citation_inputs: list[CitationInput] = state["citations"]

            if await stream_control.is_stop_requested(user_message.id):
                await self._persist_stopped(
                    user_id, conversation, user_message, final_answer
                )
                return

            async for event in self._finalize_turn(
                user_id, conversation, user_message, final_answer, citation_inputs
            ):
                yield event

        except Exception:  # noqa: BLE001 — ai.md §7: AI failures degrade
            # gracefully (an `error` SSE event + a persisted incomplete
            # message), never a crashed request; deliberately not re-raised.
            ai_status = "error"
            error_code = "generation_failed"
            await self.message_repo.create(
                user_id,
                conversation_id=conversation.id,
                role="assistant",
                content=partial_answer,
                token_count=count_tokens(partial_answer) if partial_answer else None,
                status="incomplete",
            )
            yield _sse(
                "error",
                {"code": error_code, "message": _GENERATION_FAILED_MESSAGE},
            )
        finally:
            await stream_control.mark_turn_finished(user_message.id)
            latency_ms = int((time.monotonic() - start) * 1000)
            await self.ai_request_repo.create(
                user_id,
                operation="chat",
                provider=self.llm_provider.provider_name,
                model=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                status=ai_status,
                error_code=error_code,
            )

    async def _persist_stopped(
        self,
        user_id: uuid.UUID,
        conversation: Conversation,
        user_message: Message,
        partial_content: str,
    ) -> None:
        await self.message_repo.create(
            user_id,
            conversation_id=conversation.id,
            role="assistant",
            content=partial_content,
            token_count=count_tokens(partial_content) if partial_content else None,
            status="stopped",
        )
        await self.conversation_repo.touch(conversation)

    async def _finalize_turn(
        self,
        user_id: uuid.UUID,
        conversation: Conversation,
        user_message: Message,
        final_answer: str,
        citation_inputs: list[CitationInput],
    ) -> AsyncIterator[str]:
        """Chunks the final, already-validated answer word-by-word for the
        client (mirrors FakeLLMProvider.stream()'s own established
        convention — tasks/R4-chat.md Gap 3), then persists the assistant
        message + citations and emits citations/done."""
        relayed = ""
        for word in final_answer.split(" "):
            if await stream_control.is_stop_requested(user_message.id):
                await self._persist_stopped(
                    user_id, conversation, user_message, relayed
                )
                return
            chunk = word + " "
            relayed += chunk
            yield _sse("token", {"text": chunk})

        assistant_message = await self.message_repo.create(
            user_id,
            conversation_id=conversation.id,
            role="assistant",
            content=final_answer,
            token_count=count_tokens(final_answer),
            status="complete",
        )
        citations = await self.citation_service.record_citations(
            assistant_message.id, citation_inputs
        )
        await self.conversation_repo.touch(conversation)

        yield _sse(
            "citations",
            {
                "citations": [
                    {
                        "document_id": str(c.document_id),
                        "page_number": c.page_number,
                        "snippet": c.snippet,
                        "relevance_score": c.relevance_score,
                    }
                    for c in citations
                ]
            },
        )
        yield _sse("done", {"message_id": str(assistant_message.id)})
