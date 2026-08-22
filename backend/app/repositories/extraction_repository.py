from app.models import Extraction
from app.repositories.base import TenantScopedRepository


class ExtractionRepository(TenantScopedRepository[Extraction]):
    model = Extraction
