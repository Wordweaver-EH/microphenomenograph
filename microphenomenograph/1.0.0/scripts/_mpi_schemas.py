"""Per-substep JSON schema registry for mpi_step.py."""
from __future__ import annotations
import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class SchemaError:
    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"


# ---------------------------------------------------------------------------
# Primitive validators
# ---------------------------------------------------------------------------

def _require_keys(obj: dict, keys: list[str], prefix: str) -> list[SchemaError]:
    errors = []
    for k in keys:
        if k not in obj:
            errors.append(SchemaError(f"{prefix}.{k}", f"required field missing"))
    return errors


def _reject_drift_keys(obj: dict, allowed: set[str], forbidden_aliases: dict[str, str], prefix: str) -> list[SchemaError]:
    """Reject known bad aliases (drift names) and report the correct field name."""
    errors = []
    for bad_key, good_key in forbidden_aliases.items():
        if bad_key in obj:
            errors.append(SchemaError(f"{prefix}.{bad_key}", f"unknown field; use '{good_key}' instead"))
    return errors


def _check_confidence(obj: dict, prefix: str) -> list[SchemaError]:
    conf = obj.get("confidence")
    if conf is None:
        return []
    if not isinstance(conf, int) or conf < 1 or conf > 5:
        return [SchemaError(f"{prefix}.confidence", f"must be int 1–5, got {conf!r}")]
    return []


def _check_flag_for_review(obj: dict, prefix: str) -> list[SchemaError]:
    flag = obj.get("flag_for_review")
    if flag is None:
        return []
    if not isinstance(flag, bool):
        return [SchemaError(f"{prefix}.flag_for_review", f"must be bool, got {type(flag).__name__}")]
    return []


def _check_utterance_refs(obj: dict, prefix: str) -> list[SchemaError]:
    """Require non-empty utterance_refs on every analytic unit."""
    errors = []
    refs = obj.get("utterance_refs")
    if refs is None:
        errors.append(SchemaError(f"{prefix}.utterance_refs", "missing_span_refs: required non-empty array"))
        return errors
    if not isinstance(refs, list) or len(refs) == 0:
        errors.append(SchemaError(f"{prefix}.utterance_refs", "missing_span_refs: must be a non-empty array"))
        return errors
    for i, ref in enumerate(refs):
        ref_prefix = f"{prefix}.utterance_refs[{i}]"
        if not isinstance(ref, dict):
            errors.append(SchemaError(ref_prefix, "must be an object"))
            continue
        errors.extend(_require_keys(ref, ["transcript_id", "utterance_number", "byte_start", "byte_end", "raw_excerpt"], ref_prefix))
        if "utterance_number" in ref and not isinstance(ref["utterance_number"], int):
            errors.append(SchemaError(f"{ref_prefix}.utterance_number", "must be int"))
        if "byte_start" in ref and not isinstance(ref["byte_start"], int):
            errors.append(SchemaError(f"{ref_prefix}.byte_start", "must be int"))
        if "byte_end" in ref and not isinstance(ref["byte_end"], int):
            errors.append(SchemaError(f"{ref_prefix}.byte_end", "must be int"))
    return errors


# ---------------------------------------------------------------------------
# IDU validator (shared by diachronic substeps)
# ---------------------------------------------------------------------------

# Fields required at ALL diachronic substeps
_IDU_BASE_REQUIRED = ["idu_number", "criteria", "confidence",
                      "flag_for_review", "utterance_numbers", "hinge_to_next",
                      "utterance_refs"]

# Additional fields required ONLY at idu_naming_ordering (naming must be locked)
_IDU_NAMING_REQUIRED = ["idu_name", "moment"]

# Back-compat alias: refers to the full set (idu_naming_ordering contract)
_IDU_REQUIRED = _IDU_BASE_REQUIRED + _IDU_NAMING_REQUIRED

_IDU_DRIFT_ALIASES = {
    "title": "idu_name",
    "name": "idu_name",
    "utterance_lines": "utterance_numbers",
    "utterance_ids": "utterance_numbers",
}


def _validate_idu(idu: dict, prefix: str, is_last: bool = False,
                  require_naming: bool = True) -> list[SchemaError]:
    required = _IDU_BASE_REQUIRED + (_IDU_NAMING_REQUIRED if require_naming else [])
    errors = _require_keys(idu, required, prefix)
    errors.extend(_reject_drift_keys(idu, set(_IDU_REQUIRED), _IDU_DRIFT_ALIASES, prefix))
    errors.extend(_check_confidence(idu, prefix))
    errors.extend(_check_flag_for_review(idu, prefix))
    errors.extend(_check_utterance_refs(idu, prefix))
    # hinge_to_next must be non-null for non-last IDUs
    if not is_last and "hinge_to_next" in idu and idu["hinge_to_next"] is None:
        errors.append(SchemaError(f"{prefix}.hinge_to_next", "must be a string for non-last IDU (null only allowed on last IDU)"))
    return errors


# ---------------------------------------------------------------------------
# ISU validator (shared by synchronic substeps)
# ---------------------------------------------------------------------------

# Base ISU fields — required from theme_grouping_within_idu and isu_naming.
# isu_second_level_of_abstraction is NOT required until isu_second_level_grouping.
_ISU_BASE_REQUIRED = ["isu_name", "criteria", "confidence", "flag_for_review", "utterance_refs"]
_ISU_FULL_REQUIRED = _ISU_BASE_REQUIRED + ["isu_second_level_of_abstraction"]
_ISU_DRIFT_ALIASES = {
    "isu_2nd_level": "isu_second_level_of_abstraction",
    "second_level": "isu_second_level_of_abstraction",
}


def _validate_isu(isu: dict, prefix: str, *, require_second_level: bool = False) -> list[SchemaError]:
    required = _ISU_FULL_REQUIRED if require_second_level else _ISU_BASE_REQUIRED
    errors = _require_keys(isu, required, prefix)
    errors.extend(_reject_drift_keys(isu, set(required), _ISU_DRIFT_ALIASES, prefix))
    errors.extend(_check_confidence(isu, prefix))
    errors.extend(_check_flag_for_review(isu, prefix))
    errors.extend(_check_utterance_refs(isu, prefix))
    return errors


# ---------------------------------------------------------------------------
# Per-substep schema validators
# ---------------------------------------------------------------------------

def _validate_diachronic_criteria_grouping(payload: dict) -> list[SchemaError]:
    errors = _require_keys(payload, ["analysis_type", "participant", "idus"], "payload")
    idus = payload.get("idus", [])
    if not isinstance(idus, list):
        errors.append(SchemaError("payload.idus", "must be a list"))
        return errors
    for i, idu in enumerate(idus):
        is_last = (i == len(idus) - 1)
        # idu_name and moment are NOT required at criteria_grouping/criteria_revision —
        # naming is deferred until idu_naming_ordering (analysis-fidelity AC4.1)
        errors.extend(_validate_idu(idu, f"payload.idus[{i}]", is_last=is_last,
                                    require_naming=False))
    return errors


def _validate_diachronic_criteria_revision(payload: dict) -> list[SchemaError]:
    errors = _validate_diachronic_criteria_grouping(payload)
    # Require convergence field
    conv = payload.get("convergence")
    if conv is None:
        errors.append(SchemaError("payload.convergence", "required field missing — must be {decision, reason}"))
    elif not isinstance(conv, dict):
        errors.append(SchemaError("payload.convergence", "must be an object {decision, reason}"))
    else:
        if "decision" not in conv:
            errors.append(SchemaError("payload.convergence.decision", "required; must be 'more_revision_needed' or 'converged'"))
        elif conv["decision"] not in ("more_revision_needed", "converged"):
            errors.append(SchemaError("payload.convergence.decision",
                                      f"must be 'more_revision_needed' or 'converged', got {conv['decision']!r}"))
        if "reason" not in conv:
            errors.append(SchemaError("payload.convergence.reason", "required one-sentence rationale"))
    return errors


def _validate_diachronic_idu_naming_ordering(payload: dict) -> list[SchemaError]:
    # At idu_naming_ordering, idu_name and moment MUST be populated on every IDU —
    # naming must be locked before advancing to synchronic analysis (analysis-fidelity AC4.2)
    errors = _require_keys(payload, ["analysis_type", "participant", "idus"], "payload")
    idus = payload.get("idus", [])
    if not isinstance(idus, list):
        errors.append(SchemaError("payload.idus", "must be a list"))
        return errors
    for i, idu in enumerate(idus):
        is_last = (i == len(idus) - 1)
        errors.extend(_validate_idu(idu, f"payload.idus[{i}]", is_last=is_last,
                                    require_naming=True))
    return errors


def _validate_synchronic_theme_grouping(payload: dict) -> list[SchemaError]:
    """theme_grouping_within_idu — isu_second_level_of_abstraction not yet required."""
    errors = _require_keys(payload, ["analysis_type", "participant", "idu_name", "isus"], "payload")
    # temporal_order_within_idu and concurrent_with_adjacent_idu are optional booleans/objects
    flag = payload.get("temporal_order_within_idu")
    if flag is not None and not isinstance(flag, bool):
        errors.append(SchemaError("payload.temporal_order_within_idu", "must be bool if present"))
    isus = payload.get("isus", [])
    if not isinstance(isus, list):
        errors.append(SchemaError("payload.isus", "must be a list"))
        return errors
    for i, isu in enumerate(isus):
        errors.extend(_validate_isu(isu, f"payload.isus[{i}]", require_second_level=False))
    # AC4.3: co-presence rule — temporal_order_within_idu=true requires ≥1 ISU with flag_for_review=true
    if flag is True:
        any_flagged = any(
            isinstance(isu, dict) and isu.get("flag_for_review") is True
            for isu in isus
        )
        if not any_flagged:
            errors.append(SchemaError(
                "payload.temporal_order_within_idu",
                "co-presence rule: temporal_order_within_idu=true requires "
                "at least one ISU with flag_for_review=true"
            ))
    return errors


def _validate_synchronic_isu_naming(payload: dict) -> list[SchemaError]:
    """isu_naming — isu_second_level_of_abstraction not yet required."""
    return _validate_synchronic_theme_grouping(payload)


def _validate_synchronic_isu_second_level(payload: dict) -> list[SchemaError]:
    """isu_second_level_grouping — isu_second_level_of_abstraction now required."""
    errors = _require_keys(payload, ["analysis_type", "participant", "idu_name", "isus"], "payload")
    isus = payload.get("isus", [])
    if not isinstance(isus, list):
        errors.append(SchemaError("payload.isus", "must be a list"))
        return errors
    for i, isu in enumerate(isus):
        errors.extend(_validate_isu(isu, f"payload.isus[{i}]", require_second_level=True))
    return errors


def _validate_generic_diachronic_participant_row_assembly(payload: dict) -> list[SchemaError]:
    # Orchestrator-only: no utterance_refs required (no LLM analytic units)
    return _require_keys(payload, ["event", "rows"], "payload")


def _validate_generic_diachronic_idu_similarity_grouping(payload: dict) -> list[SchemaError]:
    errors = _require_keys(payload, ["event", "idu_labels"], "payload")
    labels = payload.get("idu_labels", [])
    if isinstance(labels, list):
        for i, lbl in enumerate(labels):
            if isinstance(lbl, dict):
                errors.extend(_check_utterance_refs(lbl, f"payload.idu_labels[{i}]"))
            else:
                errors.append(SchemaError(f"payload.idu_labels[{i}]", f"must be an object, got {type(lbl).__name__}"))
    return errors


def _validate_generic_diachronic_pattern_identification(payload: dict) -> list[SchemaError]:
    errors = _require_keys(payload, ["event", "patterns"], "payload")
    patterns = payload.get("patterns", [])
    if isinstance(patterns, list):
        for i, pat in enumerate(patterns):
            if isinstance(pat, dict):
                errors.extend(_check_utterance_refs(pat, f"payload.patterns[{i}]"))
                # AC2.1: common_idus required and non-empty (invariant IDU elements)
                common = pat.get("common_idus")
                if common is None:
                    errors.append(SchemaError(
                        f"payload.patterns[{i}].common_idus",
                        "required field missing (non-empty list of common IDU labels — "
                        "IDUs appearing in ≥ 2 participants for this pattern)"
                    ))
                elif not isinstance(common, list) or len(common) == 0:
                    errors.append(SchemaError(
                        f"payload.patterns[{i}].common_idus",
                        "must be a non-empty list of common IDU labels"
                    ))
                # AC2.2: optional_idus required (may be empty — invariant patterns representable)
                if "optional_idus" not in pat:
                    errors.append(SchemaError(
                        f"payload.patterns[{i}].optional_idus",
                        "required field missing (list of optional IDU labels, may be empty)"
                    ))
                elif not isinstance(pat["optional_idus"], list):
                    errors.append(SchemaError(
                        f"payload.patterns[{i}].optional_idus",
                        "must be a list (may be empty)"
                    ))
                # AC2.1: covered_participant_keys required, non-empty list of strings
                cpk = pat.get("covered_participant_keys")
                if cpk is None:
                    errors.append(SchemaError(
                        f"payload.patterns[{i}].covered_participant_keys",
                        "required field missing (non-empty list of participant key strings, "
                        "e.g. [\"p1s1\", \"p3s1\"])"
                    ))
                elif not isinstance(cpk, list) or len(cpk) == 0:
                    errors.append(SchemaError(
                        f"payload.patterns[{i}].covered_participant_keys",
                        "must be a non-empty list of participant key strings"
                    ))
                else:
                    for j, k in enumerate(cpk):
                        if not isinstance(k, str):
                            errors.append(SchemaError(
                                f"payload.patterns[{i}].covered_participant_keys[{j}]",
                                "must be a string participant key"
                            ))
            else:
                errors.append(SchemaError(f"payload.patterns[{i}]", f"must be an object, got {type(pat).__name__}"))
    return errors


def _validate_generic_diachronic_cross_iv_contrast(payload: dict) -> list[SchemaError]:
    errors = _require_keys(payload, ["event", "contrasts"], "payload")
    contrasts = payload.get("contrasts", [])
    if isinstance(contrasts, list):
        for i, c in enumerate(contrasts):
            if isinstance(c, dict):
                errors.extend(_check_utterance_refs(c, f"payload.contrasts[{i}]"))
            else:
                errors.append(SchemaError(f"payload.contrasts[{i}]", f"must be an object, got {type(c).__name__}"))
    return errors


def _validate_generic_synchronic_select(payload: dict) -> list[SchemaError]:
    errors = _require_keys(payload, ["event", "selected_generic_idus"], "payload")
    selected = payload.get("selected_generic_idus", [])
    if isinstance(selected, list):
        for i, item in enumerate(selected):
            if isinstance(item, dict):
                errors.extend(_check_utterance_refs(item, f"payload.selected_generic_idus[{i}]"))
            else:
                errors.append(SchemaError(f"payload.selected_generic_idus[{i}]", f"must be an object, got {type(item).__name__}"))
    return errors


def _validate_generic_synchronic_worksheet_assembly(payload: dict) -> list[SchemaError]:
    # Orchestrator-only
    return _require_keys(payload, ["event", "iv_category", "generic_idu", "rows"], "payload")


def _validate_generic_synchronic_isu_second_level(payload: dict) -> list[SchemaError]:
    errors = _require_keys(payload, ["event", "iv_category", "generic_idu", "isus"], "payload")
    isus = payload.get("isus", [])
    generic_idu = payload.get("generic_idu")
    if isinstance(isus, list):
        for i, isu in enumerate(isus):
            if isinstance(isu, dict):
                errors.extend(_validate_isu(isu, f"payload.isus[{i}]", require_second_level=True))
                # AC1.1: source_generic_idu required and must match payload.generic_idu
                if "source_generic_idu" not in isu:
                    errors.append(SchemaError(
                        f"payload.isus[{i}].source_generic_idu",
                        "required field missing — must equal payload.generic_idu "
                        "(within-IDU grouping: ISUs are grouped within the target generic IDU only)"
                    ))
                elif generic_idu is not None and isu["source_generic_idu"] != generic_idu:
                    errors.append(SchemaError(
                        f"payload.isus[{i}].source_generic_idu",
                        f"must equal payload.generic_idu ({generic_idu!r}), "
                        f"got {isu['source_generic_idu']!r} — "
                        "cross-IDU synthesis belongs to global synchronic, not here"
                    ))
            else:
                errors.append(SchemaError(f"payload.isus[{i}]", f"must be an object, got {type(isu).__name__}"))
    return errors


def _validate_global_synchronic(payload: dict) -> list[SchemaError]:
    errors = _require_keys(payload, ["generic_idu", "iv_category", "isus"], "payload")
    isus = payload.get("isus", [])
    if isinstance(isus, list):
        for i, isu in enumerate(isus):
            if isinstance(isu, dict):
                errors.extend(_validate_isu(isu, f"payload.isus[{i}]", require_second_level=True))
                # AC3.1: source_event is required on each global-synchronic ISU (hard shape)
                if "source_event" not in isu:
                    errors.append(SchemaError(
                        f"payload.isus[{i}].source_event",
                        "required field missing (must name the event this ISU came from, e.g. 'event1')",
                    ))
            else:
                errors.append(SchemaError(f"payload.isus[{i}]", f"must be an object, got {type(isu).__name__}"))
    return errors


def _validate_hypothesis_evidence_extraction(payload: dict) -> list[SchemaError]:
    errors = _require_keys(payload, ["dv_focus", "evidence_items"], "payload")
    items = payload.get("evidence_items", [])
    if isinstance(items, list):
        for i, item in enumerate(items):
            if isinstance(item, dict):
                errors.extend(_check_utterance_refs(item, f"payload.evidence_items[{i}]"))
            else:
                errors.append(SchemaError(f"payload.evidence_items[{i}]", f"must be an object, got {type(item).__name__}"))
    return errors


def _validate_hypothesis_candidate_drafting(payload: dict) -> list[SchemaError]:
    errors = _require_keys(payload, ["dv_focus", "disclaimer", "candidates"], "payload")
    # Require disclaimer text
    disclaimer = payload.get("disclaimer", "")
    required_phrase = "generative conjectures"
    if isinstance(disclaimer, str) and required_phrase not in disclaimer:
        errors.append(SchemaError("payload.disclaimer",
                                  f"must contain the verbatim disclaimer phrase '{required_phrase}'"))
    candidates = payload.get("candidates", [])
    # AC2.2: claim_id must be unique across the entire artifact (all candidates)
    seen_claim_ids: set[str] = set()
    if isinstance(candidates, list):
        for i, cand in enumerate(candidates):
            if not isinstance(cand, dict):
                continue
            c_prefix = f"payload.candidates[{i}]"
            errors.extend(_require_keys(cand, ["hypothesis", "claims", "sample_summary"], c_prefix))

            # Validate sample_summary structure
            sample_summary = cand.get("sample_summary", {})
            if "sample_summary" in cand:
                if not isinstance(sample_summary, dict):
                    errors.append(SchemaError(f"{c_prefix}.sample_summary",
                                            "must be a dict"))
                elif "by_iv_level" not in sample_summary:
                    errors.append(SchemaError(f"{c_prefix}.sample_summary",
                                            "must contain 'by_iv_level' key"))

            claims = cand.get("claims", [])
            if isinstance(claims, list):
                for j, claim in enumerate(claims):
                    cl_prefix = f"{c_prefix}.claims[{j}]"
                    if not isinstance(claim, dict):
                        errors.append(SchemaError(cl_prefix, "must be an object"))
                        continue
                    # AC2.1: claim_id is required on every claim
                    errors.extend(_require_keys(claim, ["claim_id", "claim_text", "supports",
                                                         "contradicts",
                                                         "ambiguous", "n_transcripts",
                                                         "n_iv_levels_covered", "uncertainty_language",
                                                         "negative_cases"], cl_prefix))
                    # AC2.2: claim_id must be unique across the entire artifact
                    cid = claim.get("claim_id")
                    if cid is not None:
                        if cid in seen_claim_ids:
                            errors.append(SchemaError(
                                f"payload.candidates.claims",
                                f"duplicate claim_id {cid!r} — claim_id must be unique within the artifact"
                            ))
                        seen_claim_ids.add(cid)

                    # Validate that claim has at least one of: non-empty supports, non-empty contradicts, or not_applicable field
                    supports = claim.get("supports", [])
                    contradicts = claim.get("contradicts", [])
                    has_not_applicable = "not_applicable" in claim
                    supports_is_nonempty = isinstance(supports, list) and len(supports) > 0
                    contradicts_is_nonempty = isinstance(contradicts, list) and len(contradicts) > 0

                    if not (supports_is_nonempty or contradicts_is_nonempty or has_not_applicable):
                        errors.append(SchemaError(cl_prefix,
                            "must have at least one of: non-empty 'supports', non-empty 'contradicts', "
                            "or an explicit 'not_applicable' field"))

                    # Validate raw_span_refs in supports/contradicts/ambiguous
                    for evidence_type in ["supports", "contradicts", "ambiguous"]:
                        evidence_list = claim.get(evidence_type, [])
                        if isinstance(evidence_list, list):
                            for k, evidence in enumerate(evidence_list):
                                if isinstance(evidence, dict):
                                    ev_prefix = f"{cl_prefix}.{evidence_type}[{k}]"
                                    raw_refs = evidence.get("raw_span_refs", [])
                                    if not isinstance(raw_refs, list) or len(raw_refs) == 0:
                                        errors.append(SchemaError(ev_prefix,
                                                                f"must have non-empty 'raw_span_refs' list"))
                                    else:
                                        # Validate each raw_span_ref has required keys
                                        for m, ref in enumerate(raw_refs):
                                            if isinstance(ref, dict):
                                                ref_prefix = f"{ev_prefix}.raw_span_refs[{m}]"
                                                errors.extend(_require_keys(ref,
                                                    ["transcript_id", "utterance_number", "byte_start",
                                                     "byte_end", "raw_excerpt"],
                                                    ref_prefix))
                                            else:
                                                ref_prefix = f"{ev_prefix}.raw_span_refs[{m}]"
                                                errors.append(SchemaError(ref_prefix, "must be an object"))
                                else:
                                    ev_prefix = f"{cl_prefix}.{evidence_type}[{k}]"
                                    errors.append(SchemaError(ev_prefix, "must be an object"))
    return errors


def _validate_hypothesis_weak_evidence_review(payload: dict) -> list[SchemaError]:
    """Validate weak_evidence_review payload.

    Requires:
    - review_items: list of review item objects
    - claim_ids: list of claim IDs that the review covers (the roster)
    - Every entry in claim_ids must have a corresponding review_item
    - Every review_item must have a claim_id, checks dict, and outcome
    - review_items must not be empty when claim_ids is non-empty (AC2.4)
    """
    errors = _require_keys(payload, ["review_items", "claim_ids"], "payload")

    claim_ids = payload.get("claim_ids", [])
    review_items = payload.get("review_items", [])

    # Validate claim_ids is a list
    if not isinstance(claim_ids, list):
        errors.append(SchemaError("payload.claim_ids", "must be a list of claim ID strings"))
        return errors

    # Validate review_items is a list
    if not isinstance(review_items, list):
        errors.append(SchemaError("payload.review_items", "must be a list"))
        return errors

    # AC2.4: if claim_ids is non-empty, review_items must not be empty
    if len(claim_ids) > 0 and len(review_items) == 0:
        errors.append(SchemaError(
            "payload.review_items",
            "empty review_items with non-empty claim_ids: every claim must have a review item"
        ))
        return errors

    # Validate each review item shape
    reviewed_claim_ids: set[str] = set()
    for i, item in enumerate(review_items):
        item_prefix = f"payload.review_items[{i}]"
        if not isinstance(item, dict):
            errors.append(SchemaError(item_prefix, "must be an object"))
            continue
        errors.extend(_require_keys(item, ["claim_id", "checks", "outcome"], item_prefix))
        cid = item.get("claim_id")
        if cid is not None:
            reviewed_claim_ids.add(cid)
        # Validate outcome is valid
        outcome = item.get("outcome")
        if outcome is not None and outcome not in ("pass", "flagged"):
            errors.append(SchemaError(
                f"{item_prefix}.outcome",
                f"must be 'pass' or 'flagged', got {outcome!r}"
            ))
        # Validate checks is a dict
        checks = item.get("checks")
        if checks is not None and not isinstance(checks, dict):
            errors.append(SchemaError(f"{item_prefix}.checks", "must be an object"))

    # AC2.3: every claim_id in the roster must have a review item
    for cid in claim_ids:
        if cid not in reviewed_claim_ids:
            errors.append(SchemaError(
                "payload.review_items",
                f"no review item found for claim_id {cid!r} — every claim must be reviewed"
            ))

    return errors


def _validate_irr_calibration_independent_analyst(payload: dict) -> list[SchemaError]:
    return _require_keys(payload, ["stage", "participant_id", "substep_artifacts"], "payload")


def _validate_irr_calibration_alignment(payload: dict) -> list[SchemaError]:
    return _require_keys(payload, ["stage", "participant_id", "mapping",
                                   "unmatched_primary", "unmatched_alternate"], "payload")


def _validate_irr_calibration_agreement_computation(payload: dict) -> list[SchemaError]:
    return _require_keys(
        payload,
        ["stage", "participant_id", "metrics", "outcome", "rater_kind", "caveat"],
        "payload"
    )


def _validate_transcript_prep_hash_raw(payload: dict) -> list[SchemaError]:
    """hash_raw — records SHA256 and byte size of the immutable raw transcript."""
    return _require_keys(payload, ["transcript_id", "sha256", "byte_size"], "payload")


def _validate_transcript_prep_normalize(payload: dict) -> list[SchemaError]:
    """normalize — records paths of normalized transcript and diff file."""
    return _require_keys(payload, ["transcript_id", "normalized_path", "diff_path"], "payload")


def _validate_transcript_prep_register_offsets(payload: dict) -> list[SchemaError]:
    """
    register_offsets — records path of the utterance offset file and utterance count.

    In addition to required-fields validation, opens and inspects the offset file
    to reject the old array format {"transcript_id": ..., "utterances": [...]}.

    Expected flat-dict format:
        {"1": {"byte_start": N, "byte_end": N}, "2": {...}, ...}

    Keys: string utterance numbers ("1", "2", ...)
    Values: dicts with "byte_start" and "byte_end" integer fields
    """
    errors = _require_keys(payload, ["transcript_id", "offsets_path", "utterance_count"], "payload")
    if errors:
        return errors  # Can't check file if required path field is missing

    offsets_path = payload.get("offsets_path")
    # Path resolution: offsets_path is resolved relative to CWD. The schema validator
    # does not receive run_dir (unlike _validate_utterance_refs, which is passed run_dir
    # explicitly at lines 696/714 of mpi_step.py and uses run_dir/"transcripts"/"offsets").
    # Here we rely on the close-time invariant: CWD == run_dir, because all
    # `mpi_step.py close` invocations run from inside the run directory with --run-dir .
    # The file check is therefore equivalent to `(run_dir / offsets_path).exists()`.
    if offsets_path and os.path.exists(offsets_path):
        try:
            data = json.loads(open(offsets_path, encoding="utf-8").read())
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(SchemaError(
                "payload.offsets_path",
                f"offset file could not be read: {exc}"
            ))
            return errors

        # Detect old array format: top-level dict with "utterances" list key
        if isinstance(data, dict) and "utterances" in data:
            errors.append(SchemaError(
                "payload.offsets_path",
                "offset file is in the old array format "
                '({"transcript_id": ..., "utterances": [...]}) — '
                "use the flat-dict format instead: "
                '{"1": {"byte_start": N, "byte_end": N}, "2": {...}, ...}'
            ))
            return errors

        # Validate flat-dict structure
        if not isinstance(data, dict):
            errors.append(SchemaError(
                "payload.offsets_path",
                f"offset file must be a JSON object (dict), got {type(data).__name__}"
            ))
            return errors

        # Spot-check: every key should be a string-encoded integer; every value should
        # have byte_start and byte_end
        for key, entry in data.items():
            try:
                int(key)
            except (ValueError, TypeError):
                errors.append(SchemaError(
                    "payload.offsets_path",
                    f"offset file key {key!r} is not a string utterance number"
                ))
                break  # Report first bad key only
            if not isinstance(entry, dict):
                errors.append(SchemaError(
                    "payload.offsets_path",
                    f"offset file entry for utterance {key!r} must be a dict "
                    "with byte_start and byte_end"
                ))
                break
            for field in ("byte_start", "byte_end"):
                if field not in entry:
                    errors.append(SchemaError(
                        "payload.offsets_path",
                        f"offset file entry for utterance {key!r} is missing field '{field}'"
                    ))
                    break
                elif not isinstance(entry[field], int) or isinstance(entry[field], bool):
                    errors.append(SchemaError(
                        "payload.offsets_path",
                        f"offset file entry for utterance {key!r} field '{field}' must be a non-boolean int, got {type(entry[field]).__name__}"
                    ))
                    break
            if errors:
                break

    return errors


def _validate_init_scan_transcripts(payload: dict) -> list[SchemaError]:
    """scan_transcripts — records transcript IDs and their raw SHA256s."""
    return _require_keys(payload, ["transcript_ids", "raw_sha256_map"], "payload")


def _validate_init_propose_study_config(payload: dict) -> list[SchemaError]:
    """propose_study_config — optional LLM-proposed config; may be skipped."""
    return _require_keys(payload, ["event_groups_proposed"], "payload")


def _validate_init_confirm_study_config(payload: dict) -> list[SchemaError]:
    """confirm_study_config — human-confirmed study structure; writes event_groups."""
    errors = _require_keys(payload, ["event_groups", "config_provenance"], "payload")
    eg = payload.get("event_groups")
    if eg is not None:
        if not isinstance(eg, dict):
            errors.append(SchemaError("payload.event_groups", "must be a dict mapping event IDs to lists of transcript IDs"))
        else:
            for eid, tids in eg.items():
                if not isinstance(tids, list):
                    errors.append(SchemaError(f"payload.event_groups.{eid}", "must be a list of transcript ID strings"))
                else:
                    for i, tid in enumerate(tids):
                        if not isinstance(tid, str):
                            errors.append(SchemaError(f"payload.event_groups.{eid}[{i}]", "must be a string transcript ID"))
    dv = payload.get("dv_focuses")
    if dv is not None:
        if not isinstance(dv, list):
            errors.append(SchemaError("payload.dv_focuses", "must be a list of strings or null"))
        else:
            for i, f in enumerate(dv):
                if not isinstance(f, str):
                    errors.append(SchemaError(f"payload.dv_focuses[{i}]", "must be a string"))
    # Optional strict_gates: list of known gate IDs
    sg = payload.get("strict_gates")
    if sg is not None:
        if not isinstance(sg, list):
            errors.append(SchemaError("payload.strict_gates", "must be a list of gate ID strings"))
        else:
            for i, gate_id in enumerate(sg):
                if not isinstance(gate_id, str):
                    errors.append(SchemaError(f"payload.strict_gates[{i}]", "must be a string gate ID"))
                elif gate_id not in GATES:
                    errors.append(SchemaError(
                        f"payload.strict_gates[{i}]",
                        f"unknown gate ID {gate_id!r}; valid IDs: {sorted(GATES.keys())}"
                    ))
    return errors


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_VALIDATORS: dict[tuple[str, str], Any] = {
    ("init", "scan_transcripts"): _validate_init_scan_transcripts,
    ("init", "propose_study_config"): _validate_init_propose_study_config,
    ("init", "confirm_study_config"): _validate_init_confirm_study_config,
    ("diachronic", "criteria_grouping"): _validate_diachronic_criteria_grouping,
    ("diachronic", "criteria_revision"): _validate_diachronic_criteria_revision,
    ("diachronic", "idu_naming_ordering"): _validate_diachronic_idu_naming_ordering,
    ("synchronic", "theme_grouping_within_idu"): _validate_synchronic_theme_grouping,
    ("synchronic", "isu_naming"): _validate_synchronic_isu_naming,
    ("synchronic", "isu_second_level_grouping"): _validate_synchronic_isu_second_level,
    ("generic_diachronic", "participant_row_assembly"): _validate_generic_diachronic_participant_row_assembly,
    ("generic_diachronic", "idu_similarity_grouping"): _validate_generic_diachronic_idu_similarity_grouping,
    ("generic_diachronic", "pattern_identification"): _validate_generic_diachronic_pattern_identification,
    ("generic_diachronic", "cross_iv_contrast"): _validate_generic_diachronic_cross_iv_contrast,
    ("generic_synchronic", "select_generic_idus_of_interest"): _validate_generic_synchronic_select,
    ("generic_synchronic", "worksheet_assembly"): _validate_generic_synchronic_worksheet_assembly,
    ("generic_synchronic", "isu_second_level_grouping"): _validate_generic_synchronic_isu_second_level,
    ("global_synchronic", "global_synchronic"): _validate_global_synchronic,
    ("hypothesis", "evidence_extraction"): _validate_hypothesis_evidence_extraction,
    ("hypothesis", "candidate_drafting"): _validate_hypothesis_candidate_drafting,
    ("hypothesis", "weak_evidence_review"): _validate_hypothesis_weak_evidence_review,
    ("irr_calibration", "independent_analyst"): _validate_irr_calibration_independent_analyst,
    ("irr_calibration", "alignment"): _validate_irr_calibration_alignment,
    ("irr_calibration", "agreement_computation"): _validate_irr_calibration_agreement_computation,
    ("transcript_prep", "hash_raw"): _validate_transcript_prep_hash_raw,
    ("transcript_prep", "normalize"): _validate_transcript_prep_normalize,
    ("transcript_prep", "register_offsets"): _validate_transcript_prep_register_offsets,
}


def validate_units(stage: str, substep: str, payload: Any) -> list[SchemaError]:
    """
    Validate a units payload against the schema for (stage, substep).
    Returns a list of SchemaError; empty list means valid.
    """
    if not isinstance(payload, dict):
        return [SchemaError("payload", "must be a JSON object (dict)")]

    known_stages = {s for (s, _) in _VALIDATORS}
    if stage not in known_stages:
        return [SchemaError("stage", f"unknown stage '{stage}'; expected one of {sorted(known_stages)}")]

    validator = _VALIDATORS.get((stage, substep))
    if validator is None:
        return [SchemaError("substep", f"unknown substep '{substep}' for stage '{stage}'")]

    return validator(payload)


# ---------------------------------------------------------------------------
# Substep DAG (unchanged from Phase 1)
# ---------------------------------------------------------------------------

SUBSTEP_PREREQUISITES: dict[tuple[str, str], list[tuple[str, str]]] = {
    ("init", "scan_transcripts"): [],
    ("init", "propose_study_config"): [("init", "scan_transcripts")],
    # confirm_study_config depends on scan_transcripts only — propose_study_config
    # is skippable (when config_provenance is preregistered/user_specified),
    # so it cannot be a hard prerequisite.
    ("init", "confirm_study_config"): [("init", "scan_transcripts")],
    ("diachronic", "criteria_grouping"): [],
    ("diachronic", "criteria_revision"): [("diachronic", "criteria_grouping")],
    ("diachronic", "idu_naming_ordering"): [("diachronic", "criteria_revision")],
    ("synchronic", "theme_grouping_within_idu"): [("diachronic", "idu_naming_ordering")],
    ("synchronic", "isu_naming"): [("synchronic", "theme_grouping_within_idu")],
    ("synchronic", "isu_second_level_grouping"): [("synchronic", "isu_naming")],
    ("generic_diachronic", "participant_row_assembly"): [],
    ("generic_diachronic", "idu_similarity_grouping"): [("generic_diachronic", "participant_row_assembly")],
    ("generic_diachronic", "pattern_identification"): [("generic_diachronic", "idu_similarity_grouping")],
    ("generic_diachronic", "cross_iv_contrast"): [("generic_diachronic", "pattern_identification")],
    ("generic_synchronic", "select_generic_idus_of_interest"): [],
    ("generic_synchronic", "worksheet_assembly"): [("generic_synchronic", "select_generic_idus_of_interest")],
    ("generic_synchronic", "isu_second_level_grouping"): [("generic_synchronic", "worksheet_assembly")],
    ("global_synchronic", "global_synchronic"): [],
    ("hypothesis", "evidence_extraction"): [],
    ("hypothesis", "candidate_drafting"): [("hypothesis", "evidence_extraction")],
    ("hypothesis", "weak_evidence_review"): [("hypothesis", "candidate_drafting")],
    ("irr_calibration", "independent_analyst"): [],
    ("irr_calibration", "alignment"): [("irr_calibration", "independent_analyst")],
    ("irr_calibration", "agreement_computation"): [("irr_calibration", "alignment")],
    ("transcript_prep", "hash_raw"): [],
    ("transcript_prep", "normalize"): [("transcript_prep", "hash_raw")],
    # register_offsets depends on normalize (single-line-per-utterance invariant
    # enforced by normalize is assumed by the offset computation).
    ("transcript_prep", "register_offsets"): [("transcript_prep", "normalize")],
}

LLM_SUBSTEPS: frozenset[tuple[str, str]] = frozenset({
    ("diachronic", "criteria_grouping"),
    ("diachronic", "criteria_revision"),
    ("diachronic", "idu_naming_ordering"),
    ("synchronic", "theme_grouping_within_idu"),
    ("synchronic", "isu_naming"),
    ("synchronic", "isu_second_level_grouping"),
    ("generic_diachronic", "idu_similarity_grouping"),
    ("generic_diachronic", "pattern_identification"),
    ("generic_diachronic", "cross_iv_contrast"),
    ("generic_synchronic", "select_generic_idus_of_interest"),
    ("generic_synchronic", "isu_second_level_grouping"),
    ("global_synchronic", "global_synchronic"),
    ("hypothesis", "evidence_extraction"),
    ("hypothesis", "candidate_drafting"),
    ("hypothesis", "weak_evidence_review"),
    ("irr_calibration", "independent_analyst"),
    ("irr_calibration", "alignment"),
})

# ---------------------------------------------------------------------------
# Cross-scope prerequisite transforms
# ---------------------------------------------------------------------------

def _scope_strip_to_event(scope: str) -> str:
    """
    Extract the event ID from an event-category-gIDU scope string.

    Examples:
        "event3-cat-low-gidu1"      -> "event3"
        "event12-cat-moderate-gidu3" -> "event12"

    Safety: splits on "-cat-" which cannot appear in a valid event ID because
    event IDs match event\\d+ (enforced by the transcript header parser).
    If "-cat-" is not found, returns the scope unchanged (defensive fallback).
    """
    idx = scope.find("-cat-")
    if idx > 0:
        return scope[:idx]
    return scope


# Maps (downstream_stage, downstream_substep, prereq_stage, prereq_substep)
# to either:
#   - a callable(scope: str) -> str   : deterministic key derivation
#   - the sentinel "all_match"         : all matching entries in manifest must be done
#
# The cmd_close prereq loop (Phase 3) consults this table when SUBSTEP_PREREQUISITES
# lists a prereq whose scope differs from the downstream substep's scope.
PREREQ_SCOPE_TRANSFORMS: dict[tuple[str, str, str, str], object] = {
    # generic_synchronic.worksheet_assembly (scope: event<E>-cat-<C>-gidu<G>)
    # depends on select_generic_idus_of_interest (scope: event<E>)
    ("generic_synchronic", "worksheet_assembly",
     "generic_synchronic", "select_generic_idus_of_interest"): _scope_strip_to_event,

    # hypothesis.weak_evidence_review (scope: global)
    # depends on candidate_drafting (scope: dv-<focus>, one per DV focus)
    # Use all_match: every candidate_drafting entry in the manifest must be done.
    ("hypothesis", "weak_evidence_review",
     "hypothesis", "candidate_drafting"): "all_match",
}

# ---------------------------------------------------------------------------
# Cross-participant completeness gates
# ---------------------------------------------------------------------------
# Maps each cross-participant stage to the upstream substeps that must be
# done for ALL transcripts in the event before a close can proceed.
#
# Structure:
#   stage -> {
#     "scope_to_event": callable(scope: str) -> str | None,
#       # Returns the event ID to look up in event_groups.
#       # Returns None to check ALL events (global stages).
#     "required_per_transcript": list[tuple[str, str]]
#       # (stage, substep) pairs that must be done for each transcript ID
#       # in the event. For IDU-scoped stages (synchronic), the check scans
#       # all pNsN-iduK keys for that transcript.
#     "required_cross_participant": list[tuple[str | None, str, str]]
#       # (key_prefix, stage, substep) — for stages where the prereq scope is not
#       # transcript-level. Each entry: check that ANY participant key matching
#       # key_prefix has that stage/substep done.
#       # key_prefix=None → use the event ID from events_to_check (e.g. "event1")
#       # key_prefix="global" → match the literal "global" key (global_synchronic)
#       # Empty list if not applicable.
#   }
#
# Note: _scope_strip_to_event is defined in this module (Phase 2).

def _scope_to_event_all(_scope: str) -> None:  # type: ignore[return]
    """Sentinel: check ALL events (for global-scope stages)."""
    return None


COMPLETENESS_GATES: dict[str, dict] = {
    "generic_diachronic": {
        # scope: event<E>-cat-<C>
        "scope_to_event": _scope_strip_to_event,   # defined in Phase 2
        "required_per_transcript": [
            ("diachronic", "idu_naming_ordering"),
            # synchronic: all IDU scopes for the transcript must have
            # isu_second_level_grouping done — checked by scanning pNsN-iduK keys
            ("synchronic", "isu_second_level_grouping"),
        ],
        "required_cross_participant": [],
    },
    "generic_synchronic": {
        # scope: event<E>-cat-<C>-gidu<G>
        "scope_to_event": _scope_strip_to_event,
        "required_per_transcript": [],
        "required_cross_participant": [
            # key_prefix=None → match pids starting with the event ID (e.g. "event1-cat-...")
            (None, "generic_diachronic", "cross_iv_contrast"),
        ],
    },
    "global_synchronic": {
        # scope: global (or per generic-IDU × IV category)
        "scope_to_event": _scope_to_event_all,
        "required_per_transcript": [],
        "required_cross_participant": [
            # key_prefix=None → match pids starting with each event ID
            (None, "generic_synchronic", "isu_second_level_grouping"),
        ],
    },
    "hypothesis": {
        # scope: dv-<focus> or global
        "scope_to_event": _scope_to_event_all,
        "required_per_transcript": [],
        "required_cross_participant": [
            # key_prefix="gidu" → match gidu<G>-cat-<C> participant keys.
            # global_synchronic.global_synchronic is recorded under scope gidu<G>-cat-<C>
            # (confirmed: mpi-global-synchronic SKILL.md line 33; mpi-cross-analyst.md).
            # Do NOT use key_prefix=None (event-ID prefix) — gidu keys are NOT prefixed
            # by event ID.
            # Do NOT use key_prefix="global" — no participant key is literally "global".
            ("gidu", "global_synchronic", "global_synchronic"),
        ],
    },
}

# ---------------------------------------------------------------------------
# Gate registry (close-enforcement-2, Phase 1)
# ---------------------------------------------------------------------------
# Each entry: gate_id -> {stage, description, posture}
# posture:
#   "warn_or_abort"  — emit gate_warning audit event; abort only when strict
#   "downgrade"      — force substep status to "flagged"; close still succeeds
#
# Note: irr_below_threshold is a declarative registry entry only in Phase 1;
# the existing _check_irr_gate continues to emit "irr_warning" untouched.

GATES: dict[str, dict] = {
    "single_event_global_synchronic": {
        "stage": "global_synchronic",
        "description": "Global-synchronic scope covers < 2 events",
        "posture": "warn_or_abort",
    },
    "undeclared_input": {
        "stage": None,  # all cross-participant
        "description": "inputs_consumed contains path not in resolved set",
        "posture": "warn_or_abort",
    },
    "convergence_pending": {
        "stage": "diachronic",
        "description": "criteria_revision closed with more_revision_needed",
        "posture": "downgrade",
    },
    "temporal_order_pending": {
        "stage": "synchronic",
        "description": "theme_grouping_within_idu flagged temporal_order_within_idu",
        "posture": "downgrade",
    },
    "irr_below_threshold": {
        "stage": None,  # cross-participant; handled by existing _check_irr_gate
        "description": "IRR outcome is missing or low",
        "posture": "warn_or_abort",
    },
    "weak_evidence_unreviewed": {
        "stage": "hypothesis",
        "description": "weak_evidence_review has flagged items lacking acknowledged_by",
        "posture": "warn_or_abort",
    },
}

# ---------------------------------------------------------------------------
# Prompt artifact validator (schema_version 2)
# ---------------------------------------------------------------------------

_PROMPT_ARTIFACT_REQUIRED_KEYS = [
    "schema_version", "actor", "model", "sampling",
    "stage", "substep", "scope", "prompt", "response", "metadata",
]

_PROMPT_ACTOR_REQUIRED = ["kind", "name", "agent_file_sha256", "agent_file_path"]
_PROMPT_MODEL_REQUIRED = ["id", "provider"]
_PROMPT_SAMPLING_REQUIRED = ["temperature", "top_p", "max_tokens"]
_PROMPT_INNER_REQUIRED = ["system", "messages", "tools_available"]
_PROMPT_RESPONSE_REQUIRED = ["raw_text", "tool_calls", "parsed_units_path"]
_PROMPT_METADATA_REQUIRED = ["finish_reason", "usage", "duration_ms", "timestamp"]
_PROMPT_USAGE_REQUIRED = ["input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"]


def validate_prompt_artifact(
    artifact: dict,
    *,
    check_agent_sha: bool = True,
) -> list[SchemaError]:
    """
    Validate a prompt.json dict against schema_version 2.
    If check_agent_sha=True (default), reads the agent file at
    artifact['actor']['agent_file_path'] and verifies SHA256 matches
    artifact['actor']['agent_file_sha256'].
    Returns list of SchemaError; empty means valid.
    """
    import hashlib
    import os

    errors = _require_keys(artifact, _PROMPT_ARTIFACT_REQUIRED_KEYS, "prompt")

    if artifact.get("schema_version") != "2":
        errors.append(SchemaError("prompt.schema_version",
                                  f"must be '2', got {artifact.get('schema_version')!r}"))

    actor = artifact.get("actor", {})
    if isinstance(actor, dict):
        errors.extend(_require_keys(actor, _PROMPT_ACTOR_REQUIRED, "prompt.actor"))
        if check_agent_sha and "agent_file_sha256" in actor and "agent_file_path" in actor:
            agent_path = actor["agent_file_path"]
            expected_sha = actor["agent_file_sha256"]
            # Resolve relative to cwd (the plugin root during execution)
            if os.path.exists(agent_path):
                with open(agent_path, "rb") as f:
                    actual_sha = hashlib.sha256(f.read()).hexdigest()
                if actual_sha != expected_sha:
                    errors.append(SchemaError(
                        "prompt.actor.agent_file_sha256",
                        f"SHA256 mismatch: recorded={expected_sha[:16]}... "
                        f"actual={actual_sha[:16]}... — agent file has changed since this prompt was captured",
                    ))
            # If file doesn't exist at path, skip SHA check (may be a different machine/path)

    model = artifact.get("model", {})
    if isinstance(model, dict):
        errors.extend(_require_keys(model, _PROMPT_MODEL_REQUIRED, "prompt.model"))

    sampling = artifact.get("sampling", {})
    if isinstance(sampling, dict):
        errors.extend(_require_keys(sampling, _PROMPT_SAMPLING_REQUIRED, "prompt.sampling"))

    prompt_inner = artifact.get("prompt", {})
    if isinstance(prompt_inner, dict):
        errors.extend(_require_keys(prompt_inner, _PROMPT_INNER_REQUIRED, "prompt.prompt"))

    response = artifact.get("response", {})
    if isinstance(response, dict):
        errors.extend(_require_keys(response, _PROMPT_RESPONSE_REQUIRED, "prompt.response"))

    metadata = artifact.get("metadata", {})
    if isinstance(metadata, dict):
        errors.extend(_require_keys(metadata, _PROMPT_METADATA_REQUIRED, "prompt.metadata"))
        usage = metadata.get("usage", {})
        if isinstance(usage, dict):
            errors.extend(_require_keys(usage, _PROMPT_USAGE_REQUIRED, "prompt.metadata.usage"))

    return errors
