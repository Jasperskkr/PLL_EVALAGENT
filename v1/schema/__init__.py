"""Versioned, JSON-friendly data envelopes and BlockMetaSchema."""

from .envelopes import make_envelope
from .block_schema import BLOCK_SCHEMA_VERSION, build_vco_block_meta_v1, validate_block_meta
from .validators import validate_envelope, validate_system_spec_payload

__all__ = [
    "BLOCK_SCHEMA_VERSION",
    "build_vco_block_meta_v1",
    "make_envelope",
    "validate_block_meta",
    "validate_envelope",
    "validate_system_spec_payload",
]
