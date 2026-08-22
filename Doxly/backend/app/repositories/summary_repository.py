from app.models import DocumentSummary
from app.repositories.base import TenantScopedRepository


class DocumentSummaryRepository(TenantScopedRepository[DocumentSummary]):
    model = DocumentSummary
