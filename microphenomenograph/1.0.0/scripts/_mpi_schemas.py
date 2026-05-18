"""Per-substep JSON schema registry. Expanded fully in Phase 4."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class SchemaError:
    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"


def validate_units(stage: str, substep: str, payload: Any) -> list[SchemaError]:
    """
    Validate a units payload against the schema for (stage, substep).
    Returns a list of SchemaError; empty list means valid.
    Phase 1 stub: rejects non-dict payloads and unknown top-level stages.
    Phase 2 adds: IDU/ISU field name validation and confidence range checking.
    Full per-substep validation added in Phase 4.
    """
    errors = []

    if not isinstance(payload, dict):
        return [SchemaError("payload", "must be a JSON object (dict)")]

    known_stages = {
        "init", "transcript_prep", "diachronic", "synchronic",
        "generic_diachronic", "generic_synchronic", "global_synchronic",
        "hypothesis", "irr_calibration",
    }
    if stage not in known_stages:
        return [SchemaError("stage", f"unknown stage '{stage}'; expected one of {sorted(known_stages)}")]

    # Phase 2: Validate IDU/ISU field names and confidence range
    # Diachronic payloads have "idus" key
    if stage == "diachronic" and "idus" in payload:
        idus = payload.get("idus", [])
        if isinstance(idus, list):
            for i, idu in enumerate(idus):
                if isinstance(idu, dict):
                    # Check for required field: idu_name (not "title")
                    if "idu_name" not in idu and "title" in idu:
                        errors.append(SchemaError(
                            f"idus[{i}]",
                            "has 'title' but requires 'idu_name'"
                        ))
                    # Check confidence in range 1-5
                    if "confidence" in idu:
                        conf = idu["confidence"]
                        if not isinstance(conf, int) or conf < 1 or conf > 5:
                            errors.append(SchemaError(
                                f"idus[{i}].confidence",
                                f"must be integer 1-5, got {conf}"
                            ))
                    # Check flag_for_review is boolean
                    if "flag_for_review" in idu:
                        ffr = idu["flag_for_review"]
                        if not isinstance(ffr, bool):
                            errors.append(SchemaError(
                                f"idus[{i}].flag_for_review",
                                f"must be boolean, got {type(ffr).__name__}"
                            ))

    # Synchronic payloads have "isus" at top level or nested per-IDU
    if stage == "synchronic":
        # Top-level ISUs
        isus_top = payload.get("isus", [])
        if isinstance(isus_top, list):
            for i, isu in enumerate(isus_top):
                if isinstance(isu, dict):
                    # Check for required field: isu_name (not "title")
                    if "isu_name" not in isu and "title" in isu:
                        errors.append(SchemaError(
                            f"isus[{i}]",
                            "has 'title' but requires 'isu_name'"
                        ))
                    # Check confidence in range 1-5
                    if "confidence" in isu:
                        conf = isu["confidence"]
                        if not isinstance(conf, int) or conf < 1 or conf > 5:
                            errors.append(SchemaError(
                                f"isus[{i}].confidence",
                                f"must be integer 1-5, got {conf}"
                            ))

    return errors


# Substep DAG: maps (stage, substep) -> list of (stage, substep) prerequisites
# Each entry is a list of (stage, substep) that must be 'done' before this substep can close.
SUBSTEP_PREREQUISITES: dict[tuple[str, str], list[tuple[str, str]]] = {
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
}

# LLM-invoking substeps require --prompt-artifact
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
