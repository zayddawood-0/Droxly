"""
All models import here so Alembic's autogenerate (and Base.metadata) can
discover every table — app/models/__init__.py is the single import surface
alembic/env.py relies on.
"""

from app.core.database import Base
from app.models.comparison import Comparison
from app.models.conversation import (
    Citation,
    Conversation,
    ConversationDocument,
    Message,
)
from app.models.document import Document, DocumentChunk, DocumentTag, Tag
from app.models.extraction import Extraction
from app.models.observability import AiRequest, AuditLog
from app.models.summary import DocumentSummary
from app.models.user import RefreshToken, User

__all__ = [
    "AiRequest",
    "AuditLog",
    "Base",
    "Citation",
    "Comparison",
    "Conversation",
    "ConversationDocument",
    "Document",
    "DocumentChunk",
    "DocumentSummary",
    "DocumentTag",
    "Extraction",
    "Message",
    "RefreshToken",
    "Tag",
    "User",
]
