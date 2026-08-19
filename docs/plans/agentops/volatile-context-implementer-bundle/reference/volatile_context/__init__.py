"""Revision-gated volatile context reference implementation."""

from .model import (
    Binding,
    MutationIntent,
    ProjectionRequest,
    ProjectionResult,
    RevisionConflict,
)
from .projection import Projector, Provider

__all__ = [
    "Binding",
    "MutationIntent",
    "ProjectionRequest",
    "ProjectionResult",
    "Projector",
    "Provider",
    "RevisionConflict",
]
