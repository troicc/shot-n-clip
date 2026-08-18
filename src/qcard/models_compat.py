"""Small compat helpers shared by frames_packs and CLI."""

from __future__ import annotations

from .context_builder import evidence_pack_for_quote


def evidence_for_quote(source_map, exact_text):
    return evidence_pack_for_quote(source_map, exact_text)
