"""Canonical BlockMetaSchema v1 for Agent-facing behavioral blocks.

The schema is deliberately JSON-friendly and dependency free.  It freezes the
vocabulary and section boundaries; a domain pack may fill in values, but an
Agent may not silently invent a new section or change the meaning of a field.
The four contracts map directly to the project requirements:

* Interface: what the block is and how it connects;
* Behavior: variables, context and system influence;
* Capability: exported requirements and jointly feasible capabilities;
* Verification: measurement, validity and evidence quality.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Sequence


BLOCK_SCHEMA_VERSION = "block-meta-1.0"
CONTRACT_SECTIONS = (
    "interface_contract",
    "behavior_contract",
    "capability_contract",
    "verification_contract",
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

    interface = _require_mapping(value["interface_contract"], "interface_contract")
    _reject_unknown(
        interface,
        {"function", "ports", "interaction_variables"},
        "interface_contract",
    )
    if not interface.get("function"):
        raise ValueError("interface_contract.function must be non-empty")
    ports = _require_list(interface.get("ports"), "interface_contract.ports")
    for index, port in enumerate(ports):
        _validate_port(_require_mapping(port, f"ports[{index}]"), f"ports[{index}]")
    _require_list(
        interface.get("interaction_variables"),
        "interface_contract.interaction_variables",
    )

    behavior = _require_mapping(value["behavior_contract"], "behavior_contract")
    _reject_unknown(
        behavior,
        {"search_variables", "environment_contract", "system_influence_factors"},
        "behavior_contract",
    )
    for key in ("search_variables", "environment_contract", "system_influence_factors"):
        if key not in behavior:
            raise ValueError(f"behavior_contract missing field: {key}")
    for index, field in enumerate(
        _require_list(behavior["search_variables"], "behavior_contract.search_variables")
    ):
        _validate_field(
            _require_mapping(field, f"search_variables[{index}]"),
            f"search_variables[{index}]",
        )
    environment = _require_mapping(behavior["environment_contract"], "environment_contract")
    for key in ("variables", "ranges", "context_source"):
        if key not in environment:
            raise ValueError(f"environment_contract missing field: {key}")
    _reject_unknown(
        environment,
        {"variables", "ranges", "context_source"},
        "environment_contract",
    )
    _require_list(environment["variables"], "environment_contract.variables")
    _require_mapping(environment["ranges"], "environment_contract.ranges")
    influences = _require_list(
        behavior["system_influence_factors"],
        "behavior_contract.system_influence_factors",
    )
    for index, influence in enumerate(influences):
        item = _require_mapping(influence, f"system_influence_factors[{index}]")
        for key in ("source", "target", "mechanism", "evidence_id"):
            if key not in item:
                raise ValueError(f"system_influence_factors[{index}] missing field: {key}")
        _reject_unknown(
            item,
            {"source", "target", "mechanism", "evidence_id"},
            f"system_influence_factors[{index}]",
        )

    capability = _require_mapping(value["capability_contract"], "capability_contract")
    _reject_unknown(
        capability,
        {"exported_specs", "capability_region", "tradeoffs"},
        "capability_contract",
    )
    for key in ("exported_specs", "capability_region", "tradeoffs"):
        if key not in capability:
            raise ValueError(f"capability_contract missing field: {key}")
    for index, field in enumerate(
        _require_list(capability["exported_specs"], "capability_contract.exported_specs")
    ):
        _validate_field(
            _require_mapping(field, f"exported_specs[{index}]"),
            f"exported_specs[{index}]",
        )
    region = _require_mapping(capability["capability_region"], "capability_region")
    for key in ("representation", "dimensions", "formal_status"):
        if key not in region:
            raise ValueError(f"capability_region missing field: {key}")
    _require_list(region["dimensions"], "capability_region.dimensions")
    tradeoffs = _require_list(capability["tradeoffs"], "capability_contract.tradeoffs")
    for index, tradeoff in enumerate(tradeoffs):
        item = _require_mapping(tradeoff, f"tradeoffs[{index}]")
        for key in ("variables", "status", "evidence_ids"):
            if key not in item:
                raise ValueError(f"tradeoffs[{index}] missing field: {key}")

    verification = _require_mapping(value["verification_contract"], "verification_contract")
    _reject_unknown(
        verification,
        {"measurement_contracts", "validity_domain", "uncertainty", "evidence"},
        "verification_contract",
    )
    for key in (
        "measurement_contracts",
        "validity_domain",
        "uncertainty",
        "evidence",
    ):
        if key not in verification:
            raise ValueError(f"verification_contract missing field: {key}")
    measurements = _require_list(
        verification["measurement_contracts"],
        "verification_contract.measurement_contracts",
    )
    for index, measurement in enumerate(measurements):
        item = _require_mapping(measurement, f"measurement_contracts[{index}]")
        for key in ("id", "metric", "method", "stimulus", "context_source", "aggregation"):
            if key not in item:
                raise ValueError(f"measurement_contracts[{index}] missing field: {key}")
    _require_mapping(verification["validity_domain"], "verification_contract.validity_domain")
    uncertainty = _require_mapping(
        verification["uncertainty"], "verification_contract.uncertainty"
    )
    for key in ("quantified", "type"):
        if key not in uncertainty:
            raise ValueError(f"verification_contract.uncertainty missing field: {key}")
    evidence = _require_list(verification["evidence"], "verification_contract.evidence")
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


def build_vco_block_meta_v1(
    contract: Mapping[str, Any],
    *,
    allocation_evidence_id: str = "allocation:v1:pn_1mhz_to_integrated_jitter",
) -> Dict[str, Any]:
    """Build the canonical VCO instance of BlockMetaSchema v1.

    The instance exposes only variables already supported by the current VCO
    model.  It explicitly marks capability as sampled/partial so that adding a
    schema does not overclaim a multi-dimensional VCO feasibility region.
    """

    fields = {str(item.get("name")): item for item in contract.get("fields", [])}
    vctrl_range = fields.get("Vctrl", {}).get("range", [0.1, 1.1])
    temperature_range = fields.get("temperature", {}).get("range", [-40.0, 125.0])
    validity = dict(contract.get("validity", {}))
    meta: Dict[str, Any] = {
        "schema_version": BLOCK_SCHEMA_VERSION,
        "object_type": "block_meta",
        "block_id": "VCO",
        "block_type": "vco",
        "provenance": {
            "source_contract_id": contract.get("contract_id"),
            "status": "schema_instance; behavioral_validity_requires_tb",
        },
        "interface_contract": {
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
                    "name": "temperature",
                    "direction": "in",
                    "signal_type": "environment",
                    "unit": "degC",
                    "datatype": "float",
                    "range": list(temperature_range),
                },
                {
                    "name": "oscillation_frequency",
                    "direction": "out",
                    "signal_type": "frequency",
                    "unit": "Hz",
                    "datatype": "float",
                },
                {
                    "name": "phase_noise_profile",
                    "direction": "out",
                    "signal_type": "ssb_phase_noise",
                    "unit": "dBc/Hz",
                    "datatype": "function(offset_hz)",
                },
                {
                    "name": "Kvco",
                    "direction": "out",
                    "signal_type": "local_tuning_slope",
                    "unit": "Hz/V",
                    "datatype": "float",
                },
            ],
            "interaction_variables": [
                "VCO.vctrl",
                "VCO.oscillation_frequency",
                "VCO.phase_noise_profile",
                "VCO.Kvco",
            ],
        },
        "behavior_contract": {
            "search_variables": [
                _field(
                    "phase_noise_1mhz_dbc_hz",
                    "design_variable",
                    "dBc/Hz",
                    "float",
                    ["Vctrl", "temperature", "power"],
                    "deterministic PN parameter sweep",
                    "1 MHz phase-noise allocation knob in V1.",
                    validity,
                ),
                _field(
                    "k1_hz_per_v",
                    "design_variable",
                    "Hz/V",
                    "float",
                    ["Vctrl"],
                    "deterministic SystemTB sweep",
                    "First-order tuning coefficient exposed for sensitivity evidence.",
                    validity,
                ),
                _field(
                    "vctrl_max_v",
                    "design_variable",
                    "V",
                    "float",
                    [],
                    "deterministic SystemTB sweep",
                    "Control-voltage envelope knob used in V1 evidence.",
                    validity,
                ),
                _field(
                    "nominal_power_w",
                    "design_variable",
                    "W",
                    "float",
                    ["Vctrl", "temperature"],
                    "deterministic SystemTB sweep",
                    "Behavioral power knob available for residual-driven exploration.",
                    validity,
                ),
            ],
            "environment_contract": {
                "variables": ["Vctrl", "temperature", "vdd_v"],
                "ranges": {
                    "Vctrl": list(vctrl_range),
                    "temperature_c": list(temperature_range),
                },
                "context_source": "SystemTB operating envelope",
            },
            "system_influence_factors": [
                {
                    "source": "phase_noise_1mhz_dbc_hz",
                    "target": "PLL.integrated_jitter",
                    "mechanism": "VCO noise transfer followed by phase-noise integration",
                    "evidence_id": allocation_evidence_id,
                },
                {
                    "source": "k1_hz_per_v",
                    "target": "PLL.lock_time",
                    "mechanism": "effective PLL dynamics / loop bandwidth",
                    "evidence_id": "sensitivity:k1_hz_per_v:lock_time",
                },
            ],
        },
        "capability_contract": {
            "exported_specs": [
                _field(
                    "phase_noise_1mhz_max_dbc_hz",
                    "hard_constraint",
                    "dBc/Hz",
                    "float",
                    ["Vctrl", "temperature", "power"],
                    "context-aware VCO BlockTB",
                    "Maximum allowed phase noise at 1 MHz over the SystemTB envelope.",
                    validity,
                ),
                _field(
                    "kvco_range_hz_per_v",
                    "hard_constraint",
                    "Hz/V",
                    "interval",
                    ["Vctrl"],
                    "context-aware VCO BlockTB",
                    "Optional Kvco range requirement reserved for multi-parameter allocation.",
                    validity,
                ),
                _field(
                    "power_max_w",
                    "hard_constraint",
                    "W",
                    "float",
                    ["Vctrl", "temperature"],
                    "context-aware VCO BlockTB",
                    "Optional VCO power upper bound.",
                    validity,
                ),
            ],
            "capability_region": {
                "representation": "sampled_feasible_points",
                "dimensions": ["phase_noise_1mhz_dbc_hz"],
                "formal_status": "v1_one_dimensional_only",
                "future_dimensions": ["k1_hz_per_v", "tuning_range_hz", "power_w"],
            },
            "tradeoffs": [
                {
                    "variables": ["phase_noise_1mhz_dbc_hz", "k1_hz_per_v"],
                    "status": "sensitivity_evidence_only",
                    "evidence_ids": [
                        "sensitivity:pn_1mhz_dbc_hz:integrated_jitter",
                        "sensitivity:k1_hz_per_v:lock_time",
                    ],
                }
            ],
        },
        "verification_contract": {
            "measurement_contracts": [
                {
                    "id": "measurement:vco:phase_noise_1mhz",
                    "metric": "phase_noise_1mhz_dbc_hz",
                    "method": "behavioral_psd_evaluation",
                    "stimulus": "steady_state_system_context",
                    "offset_hz": 1.0e6,
                    "context_source": "SystemTB operating envelope",
                    "aggregation": "worst_case_over_context",
                },
                {
                    "id": "measurement:vco:kvco",
                    "metric": "kvco_hz_per_v",
                    "method": "local_derivative_of_tuning_curve",
                    "stimulus": "Vctrl sweep",
                    "context_source": "SystemTB operating envelope",
                    "aggregation": "range_over_context",
                },
            ],
            "validity_domain": {
                "contract_validity": validity,
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
