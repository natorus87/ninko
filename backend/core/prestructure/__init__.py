"""Deterministic task pre-structuring for Ninko.

This package provides components to transform user messages into structured
TaskSketch objects before planner execution. All operations are deterministic
and do not use LLM calls or tool execution.
"""

from core.prestructure.schemas import (
    TaskSketch,
    SourceInfo,
    TaskInfo,
    RiskInfo,
    ScopeInfo,
    ScopeEntities,
    ConstraintInfo,
    RoutingHints,
    UncertaintyInfo,
    DebugInfo,
    RankedModule,
    ModuleMetadata,
    TaskSketchBuildResult,
    Intent,
    Complexity,
    RiskLevel,
    ExecutionMode,
    WorkerType,
    Domain,
)
from core.prestructure.task_sketch_builder import (
    DeterministicTaskSketchBuilder,
    build_task_sketch,
)
from core.prestructure.normalizer import (
    InputNormalizer,
    NormalizedInput,
    normalize,
    quick_normalize,
)
from core.prestructure.intent_detector import (
    IntentDetector,
    detect_intent,
    detect_intent_with_confidence,
)
from core.prestructure.risk_assessor import (
    RiskAssessor,
    assess_risk,
)
from core.prestructure.entity_extractor import (
    EntityExtractor,
    extract_entities,
    extract_domain,
)
from core.prestructure.module_ranker import (
    ModuleRanker,
    rank_modules,
    create_module_metadata_from_registry,
)
from core.prestructure.routing_hints import (
    RoutingHintInferencer,
    infer_routing_hints,
)

__all__ = [
    # Main builder
    "DeterministicTaskSketchBuilder",
    "build_task_sketch",
    # Schemas
    "TaskSketch",
    "SourceInfo",
    "TaskInfo",
    "RiskInfo",
    "ScopeInfo",
    "ScopeEntities",
    "ConstraintInfo",
    "RoutingHints",
    "UncertaintyInfo",
    "DebugInfo",
    "RankedModule",
    "ModuleMetadata",
    "TaskSketchBuildResult",
    # Types
    "Intent",
    "Complexity",
    "RiskLevel",
    "ExecutionMode",
    "WorkerType",
    "Domain",
    # Components
    "InputNormalizer",
    "NormalizedInput",
    "normalize",
    "quick_normalize",
    "IntentDetector",
    "detect_intent",
    "detect_intent_with_confidence",
    "RiskAssessor",
    "assess_risk",
    "EntityExtractor",
    "extract_entities",
    "extract_domain",
    "ModuleRanker",
    "rank_modules",
    "create_module_metadata_from_registry",
    "RoutingHintInferencer",
    "infer_routing_hints",
]
