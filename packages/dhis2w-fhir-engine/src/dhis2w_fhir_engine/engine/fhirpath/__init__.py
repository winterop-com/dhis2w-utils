"""FHIRPath evaluator."""

# Importing the function package registers every FHIRPath function on the shared registry.
from . import functions  # noqa: F401  # pyright: ignore[reportUnusedImport]
from .evaluator import FHIRPathEvaluator, evaluate
from .visitor import unwrap_primitives

__all__ = ["FHIRPathEvaluator", "evaluate", "unwrap_primitives"]
