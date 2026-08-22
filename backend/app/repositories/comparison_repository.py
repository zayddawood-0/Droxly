from app.models import Comparison
from app.repositories.base import TenantScopedRepository


class ComparisonRepository(TenantScopedRepository[Comparison]):
    model = Comparison
