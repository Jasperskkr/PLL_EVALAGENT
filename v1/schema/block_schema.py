"""Canonical BlockMetaSchema v1 for Agent-facing behavioral blocks.

The schema is deliberately JSON-friendly and dependency free.  It freezes the
vocabulary and section boundaries; a domain pack may fill in values, but an
Agent may not silently invent a new section or change the meaning of a field.
The four sections map directly to the frozen Block Graph semantics:

* Architecture: what the block is and how it connects;
* Behavior: actual block metrics under context;
* Influence: how block behavior affects system metrics;
* Evidence: measurement, validity and evidence quality.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Sequence


BLOCK_SCHEMA_VERSION = "block-meta-1.0"
CONTRACT_SECTIONS = (
    "architecture",
    "behavior",
    "influence",
    "evidence",
)
FIELD_ROLES = frozenset(
    {
        "system_context",
        "design_variable",
        "intermediate_variable",
        "performance_metric",
        "hard_constraint",
        "objective",
        "validity_condition",
        "interaction_variable",
    }
)
PORT_DIRECTIONS = frozenset({"in", "out", "inout"})
TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "object_type",
        "block_id",
        "block_type",
        "provenance",
        *CONTRACT_SECTIONS,
    }
)


def _reject_unknown(value: Mapping[str, Any], allowed: Iterable[str], name: str) -> None:
    unknown = set(value) - set(allowed)
    if unknown:
        raise ValueError(f"{name} has unsupported field(s): {sorted(unknown)}")


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _require_list(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be an array")
    return value


def _validate_field(field: Mapping[str, Any], location: str) -> None:
    _reject_unknown(
        field,
        {
            "name",
            "role",
            "unit",
            "datatype",
            "depends_on",
            "evaluation_method",
            "description",
            "validity",
        },
        location,
    )
    for key in ("name", "role", "unit", "datatype", "depends_on", "description"):
        if key not in field:
            raise ValueError(f"{location} missing field: {key}")
    if field["role"] not in FIELD_ROLES:
        raise ValueError(f"{location} has unsupported role: {field['role']}")
    if not isinstance(field["depends_on"], list):
        raise ValueError(f"{location}.depends_on must be an array")
    if "evaluation_method" not in field and field["role"] != "system_context":
        raise ValueError(f"{location} requires evaluation_method")


def _validate_port(port: Mapping[str, Any], location: str) -> None:
    _reject_unknown(
        port,
        {"name", "direction", "signal_type", "unit", "datatype", "range", "description"},
        location,
    )
    for key in ("name", "direction", "signal_type", "unit", "datatype"):
        if key not in port:
            raise ValueError(f"{location} missing field: {key}")
    if port["direction"] not in PORT_DIRECTIONS:
        raise ValueError(f"{location} has unsupported direction: {port['direction']}")


def validate_block_meta(value: Mapping[str, Any]) -> None:
    """Validate a BlockMetaSchema v1 instance.

    This validator checks structure and vocabulary only.  Feasibility and
    system performance remain the responsibility of deterministic BlockTB and
    SystemTB; schema validity must never be confused with behavioral validity.
    """

    for key in ("schema_version", "object_type", "block_id", "block_type"):
        if key not in value:
            raise ValueError(f"block meta missing required field: {key}")
    if value["schema_version"] != BLOCK_SCHEMA_VERSION:
        raise ValueError(f"unsupported block schema: {value['schema_version']}")
    if value["object_type"] != "block_meta":
        raise ValueError("block meta object_type must be block_meta")
    if not value["block_id"] or not value["block_type"]:
        raise ValueError("block_id and block_type must be non-empty")
    _reject_unknown(value, TOP_LEVEL_KEYS, "block meta")

    for section in CONTRACT_SECTIONS:
        if section not in value:
            raise ValueError(f"block meta missing contract section: {section}")

    architecture = _require_mapping(value["architecture"], "architecture")
    _reject_unknown(
        architecture,
        {"function", "ports", "context_inputs", "connections"},
        "architecture",
    )
    if not architecture.get("function"):
        raise ValueError("architecture.function must be non-empty")
    ports = _require_list(architecture.get("ports"), "architecture.ports")
    for index, port in enumerate(ports):
        port_value = _require_mapping(port, f"ports[{index}]")
        _validate_port(port_value, f"ports[{index}]")
        port_name = str(port_value.get("name", "")).lower()
        if any(token in port_name for token in ("phase_noise", "kvco", "power")):
            raise ValueError(f"architecture port cannot be a behavior metric: {port_name}")
    _require_list(architecture.get("context_inputs"), "architecture.context_inputs")
    _require_list(architecture.get("connections"), "architecture.connections")

    behavior = _require_mapping(value["behavior"], "behavior")
    _reject_unknown(
        behavior,
        {"metrics", "context_dependencies", "evaluation_methods"},
        "behavior",
    )
    for key in ("metrics", "context_dependencies", "evaluation_methods"):
        if key not in behavior:
            raise ValueError(f"behavior missing field: {key}")
    for index, field in enumerate(
        _require_list(behavior["metrics"], "behavior.metrics")
    ):
        _validate_field(
            _require_mapping(field, f"metrics[{index}]"),
            f"metrics[{index}]",
        )
        if field["role"] != "performance_metric":
            raise ValueError(f"behavior metric cannot be a model knob: {field['name']}")
    environment = _require_mapping(behavior["context_dependencies"], "context_dependencies")
    for key in ("variables", "ranges", "context_source"):
        if key not in environment:
            raise ValueError(f"context_dependencies missing field: {key}")
    _reject_unknown(
        environment,
        {"variables", "architecture_context_variables", "ranges", "context_source"},
        "context_dependencies",
    )
    _require_list(environment["variables"], "context_dependencies.variables")
    _require_mapping(environment["ranges"], "context_dependencies.ranges")
    _require_mapping(behavior["evaluation_methods"], "behavior.evaluation_methods")

    influences = _require_list(value["influence"], "influence")
    for index, influence in enumerate(influences):
        item = _require_mapping(influence, f"influence[{index}]")
        for key in (
            "source_behavior_metric",
            "target_system_metric",
            "mechanism",
            "evidence_refs",
            "validity_domain",
        ):
            if key not in item:
                raise ValueError(f"influence[{index}] missing field: {key}")
        _reject_unknown(
            item,
            {
                "source_behavior_metric",
                "target_system_metric",
                "mechanism",
                "evidence_refs",
                "validity_domain",
            },
            f"influence[{index}]",
        )
        _require_list(item["evidence_refs"], f"influence[{index}].evidence_refs")
        validity_domain = _require_mapping(
            item["validity_domain"], f"influence[{index}].validity_domain"
        )
        for key in ("declared_domain", "validated_domain"):
            if key not in validity_domain:
                raise ValueError(
                    f"influence[{index}].validity_domain missing field: {key}"
                )

    evidence_section = _require_mapping(value["evidence"], "evidence")
    _reject_unknown(
        evidence_section,
        {"measurement_contracts", "validity_domain", "uncertainty", "evidence"},
        "evidence",
    )
    for key in (
        "measurement_contracts",
        "validity_domain",
        "uncertainty",
        "evidence",
    ):
        if key not in evidence_section:
            raise ValueError(f"evidence missing field: {key}")
    measurements = _require_list(
        evidence_section["measurement_contracts"],
        "evidence.measurement_contracts",
    )
    for index, measurement in enumerate(measurements):
        item = _require_mapping(measurement, f"measurement_contracts[{index}]")
        for key in ("id", "metric", "method", "stimulus", "context_source", "aggregation"):
            if key not in item:
                raise ValueError(f"measurement_contracts[{index}] missing field: {key}")
    evidence_validity = _require_mapping(
        evidence_section["validity_domain"], "evidence.validity_domain"
    )
    for key in ("declared_domain", "validated_domain"):
        if key not in evidence_validity:
            raise ValueError(f"evidence.validity_domain missing field: {key}")
    uncertainty = _require_mapping(
        evidence_section["uncertainty"], "evidence.uncertainty"
    )
    for key in ("quantified", "type"):
        if key not in uncertainty:
            raise ValueError(f"evidence.uncertainty missing field: {key}")
    evidence = _require_list(evidence_section["evidence"], "evidence.evidence")
    for index, evidence_item in enumerate(evidence):
        item = _require_mapping(evidence_item, f"evidence[{index}]")
        for key in ("id", "kind", "status"):
            if key not in item:
                raise ValueError(f"evidence[{index}] missing field: {key}")


def _field(
    name: str,
    role: str,
    unit: str,
    datatype: str,
    depends_on: Iterable[str],
    evaluation_method: str,
    description: str,
    validity: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "name": name,
        "role": role,
        "unit": unit,
        "datatype": datatype,
        "depends_on": list(depends_on),
        "evaluation_method": evaluation_method,
        "description": description,
    }
    if validity is not None:
        result["validity"] = dict(validity)
    return result


def _default_validated_domain() -> Dict[str, Any]:
    return {
        "temperature_c": [25.0],
        "validation_source": "v1_observation_holdout",
    }


def build_vco_block_meta_v1(
    contract: Mapping[str, Any],
    *,
    validated_domain: Mapping[str, Any] | None = None,
    allocation_evidence_id: str = "allocation:v1:pn_anchor_to_measured_worst_pn_to_integrated_jitter",
) -> Dict[str, Any]:
    """Build the canonical VCO instance of BlockMetaSchema v1.

    The instance exposes only variables already supported by the current VCO
    model.  It explicitly marks capability as sampled/partial so that adding a
    schema does not overclaim a multi-dimensional VCO feasibility region.
    """

    fields = {str(item.get("name")): item for item in contract.get("fields", [])}
    vctrl_range = fields.get("Vctrl", {}).get("range", [0.1, 1.1])
    temperature_range = fields.get("temperature", {}).get("range", [-40.0, 125.0])
    declared_domain = dict(contract.get("validity", {}))
    validation_domain = dict(validated_domain or _default_validated_domain())
    domain_contract = {
        "declared_domain": declared_domain,
        "validated_domain": validation_domain,
    }
    meta: Dict[str, Any] = {
        "schema_version": BLOCK_SCHEMA_VERSION,
        "object_type": "block_meta",
        "block_id": "VCO",
        "block_type": "vco",
        "provenance": {
            "source_contract_id": contract.get("contract_id"),
            "status": "schema_instance; behavioral_validity_requires_tb",
        },
        "architecture": {
            "function": "Generate a context-dependent oscillator frequency and phase-noise output for the PLL.",
            "ports": [
                {
                    "name": "Vctrl",
                    "direction": "in",
                    "signal_type": "control_voltage",
                    "unit": "V",
                    "datatype": "float",
                    "range": list(vctrl_range),
                },
                {
                    "name": "oscillation_frequency",
                    "direction": "out",
                    "signal_type": "frequency",
                    "unit": "Hz",
                    "datatype": "float",
                },
            ],
            "context_inputs": ["Environment.temperature", "Environment.vdd"],
            "connections": ["PLL.control_voltage -> VCO.vctrl", "VCO.oscillation -> PLL.oscillation"],
        },
        "behavior": {
            "metrics": [
                _field(
                    "frequency_hz",
                    "performance_metric",
                    "Hz",
                    "float",
                    ["Vctrl", "temperature"],
                    "frequency_hz(Vctrl, temperature)",
                    "Oscillation frequency under the frozen context.",
                    domain_contract,
                ),
                _field(
                    "phase_noise_1mhz_dbc_hz",
                    "performance_metric",
                    "dBc/Hz",
                    "float",
                    ["Vctrl", "temperature", "power_w"],
                    "phase_noise_dbc_hz(1MHz, Vctrl, temperature, power)",
                    "Point phase-noise behavior at 1 MHz under a specific context.",
                    domain_contract,
                ),
                _field(
                    "kvco_hz_per_v",
                    "performance_metric",
                    "Hz/V",
                    "float",
                    ["Vctrl"],
                    "local_derivative_of_tuning_curve",
                    "Local tuning gain df/dVctrl.",
                    domain_contract,
                ),
                _field(
                    "power_w",
                    "performance_metric",
                    "W",
                    "float",
                    ["Vctrl", "temperature"],
                    "power_w(Vctrl, temperature)",
                    "Point VCO power under a specific context.",
                    domain_contract,
                ),
            ],
            "context_dependencies": {
                "variables": ["Vctrl", "temperature"],
                "architecture_context_variables": ["vdd_v"],
                "ranges": {
                    "Vctrl": list(vctrl_range),
                    "temperature_c": list(temperature_range),
                },
                "context_source": "VCOBlockContext.v1",
            },
            "evaluation_methods": {
                "frequency_hz": "behavioral_vco_frequency",
                "phase_noise_1mhz_dbc_hz": "behavioral_psd_evaluation",
                "kvco_hz_per_v": "local_derivative_of_tuning_curve",
                "power_w": "behavioral_power_model",
            },
        },
        "influence": [
            {
                "source_behavior_metric": "phase_noise_1mhz_dbc_hz",
                "target_system_metric": "integrated_jitter_s",
                "mechanism": "VCO noise transfer followed by phase-noise integration",
                "evidence_refs": [allocation_evidence_id, "Evidence.sensitivity"],
                "validity_domain": domain_contract,
            },
            {
                "source_behavior_metric": "kvco_hz_per_v",
                "target_system_metric": "integrated_jitter_s",
                "mechanism": "loop bandwidth changes VCO noise integration",
                "evidence_refs": ["Evidence.sensitivity"],
                "validity_domain": domain_contract,
            },
            {
                "source_behavior_metric": "kvco_hz_per_v",
                "target_system_metric": "lock_time_s",
                "mechanism": "effective PLL dynamics / loop bandwidth",
                "evidence_refs": ["sensitivity:k1_hz_per_v:lock_time"],
                "validity_domain": domain_contract,
            },
            {
                "source_behavior_metric": "frequency_hz",
                "target_system_metric": "output_frequency_hz",
                "mechanism": "divider feedback",
                "evidence_refs": ["SystemTB"],
                "validity_domain": domain_contract,
            },
            {
                "source_behavior_metric": "power_w",
                "target_system_metric": "power_w",
                "mechanism": "block power aggregation",
                "evidence_refs": ["SystemTB"],
                "validity_domain": domain_contract,
            },
        ],
        "evidence": {
            "measurement_contracts": [
                {
                    "id": "measurement:vco:phase_noise_1mhz",
                    "metric": "phase_noise_1mhz_dbc_hz",
                    "measured_metric": "worst_phase_noise_1mhz_dbc_hz",
                    "method": "behavioral_psd_evaluation",
                    "stimulus": "frozen_vco_block_context_sweep",
                    "offset_hz": 1.0e6,
                    "context_source": "VCOBlockContext.v1",
                    "aggregation": "worst_case_over_context",
                },
                {
                    "id": "measurement:vco:kvco",
                    "metric": "kvco_hz_per_v",
                    "method": "local_derivative_of_tuning_curve",
                    "stimulus": "Vctrl sweep",
                    "context_source": "VCOBlockContext.v1",
                    "aggregation": "range_over_context",
                },
            ],
            "validity_domain": {
                "declared_domain": declared_domain,
                "validated_domain": validation_domain,
                "model_fidelity": "synthetic_behavioral",
                "out_of_domain_policy": "reject_or_recharacterize",
            },
            "uncertainty": {
                "quantified": False,
                "type": "model_fidelity_not_signoff_calibrated",
                "required_future_evidence": ["engineering_data_correlation"],
            },
            "evidence": [
                {
                    "id": "contract:vco:v1",
                    "kind": "contract_observation_holdout",
                    "status": contract.get("status", "hypothesis"),
                },
                {
                    "id": allocation_evidence_id,
                    "kind": "system_to_block_allocation",
                    "status": "deterministic_v1_proof",
                },
            ],
        },
    }
    validate_block_meta(meta)
    return meta
