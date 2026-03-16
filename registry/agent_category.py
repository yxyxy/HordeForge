from enum import Enum


class AgentCategory(Enum):
    """
    Перечисление категорий агентов для классификации агентов в системе.
    """

    PLANNING = "planning"
    GENERATION = "generation"
    VALIDATION = "validation"
    INFRASTRUCTURE = "infrastructure"
    ORCHESTRATION = "orchestration"
    SCANNING = "scanning"
    MONITORING = "monitoring"
    SECURITY = "security"
    DEVELOPMENT = "development"
    TESTING = "testing"
    REVIEW = "review"
    FIX = "fix"
    DEPLOYMENT = "deployment"
