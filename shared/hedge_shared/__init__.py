"""HEDGE-ExpertAI shared package — models, config, and utilities."""

__version__ = "0.1.0"
from .models_v2 import (
    AppMetadataV2,
    ChatRequestV2,
    RecommendationEventRequest,
    SearchFilters,
    SearchRequestV2,
    SemanticAnnotation,
)
from .production import validate_production_environment

__all__ = [
    "AppMetadataV2",
    "ChatRequestV2",
    "RecommendationEventRequest",
    "SearchFilters",
    "SearchRequestV2",
    "SemanticAnnotation",
    "validate_production_environment",
]
