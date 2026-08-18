"""Deterministic V3 editorial quality gate (no runtime LLM calls)."""
from .common import (Report, SCHEMA_VERSION, awkward_zh_flags,
                     detect_context_dependency, similarity)
from .candidate import validate_candidate_pool
from .selection import validate_selection_audit
from .translation import validate_pack_binding, validate_translation_audit
from .stages import (prepare_inputs, validate_candidate_stage,
                     validate_selection_stage, validate_translation_stage,
                     validate_work_dir)

__all__ = [
    "Report", "SCHEMA_VERSION", "awkward_zh_flags",
    "detect_context_dependency", "similarity", "validate_candidate_pool",
    "validate_selection_audit", "validate_pack_binding",
    "validate_translation_audit", "prepare_inputs",
    "validate_candidate_stage", "validate_selection_stage",
    "validate_translation_stage", "validate_work_dir",
]
