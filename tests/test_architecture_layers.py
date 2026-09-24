"""Layer rules and runtime closure contracts, independent of import aliases."""

import ast
from copy import deepcopy
from dataclasses import replace
from importlib.util import resolve_name
from pathlib import Path
import subprocess
import sys

import pytest

from v1.evaluation import system, vco
from v1.model.pll_behavioral import VCOParams
from v1.specs import SystemSpec, VCORequirement, load_case
from v1.api.verification import VerificationRequest
from v1.verification.service import verify_block_assignment

ROOT = Path(__file__).resolve().parents[1]


def imports(path):
    package = ".".join(path.relative_to(ROOT).with_suffix("").parts[:-1])
    if path.name == "__init__.py":
        package = ".".join(path.parent.relative_to(ROOT).parts)
    targets = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            target = resolve_name("." * node.level + (node.module or ""), package) if node.level else node.module
            targets.add(target)
            targets.update(target + "." + alias.name for alias in node.names)
    return targets


@pytest.mark.parametrize("layer,forbidden", [
    ("api", ("evaluation", "allocation", "verification", "workflow", "backends", "graph", "schema", "pipeline")),
    ("model", ("api", "evaluation", "allocation", "verification", "workflow", "backends", "graph", "schema", "pipeline")),
    ("evaluation", ("api", "allocation", "verification", "workflow", "backends", "graph", "schema", "pipeline")),
    ("schema", ("evaluation", "allocation", "verification", "workflow", "backends", "graph", "pipeline")),
    ("graph", ("allocation", "verification", "workflow", "backends", "pipeline")),
    ("allocation", ("graph", "workflow", "pipeline")),
    ("verification", ("allocation", "graph", "workflow", "pipeline")),
    ("workflow", ("pipeline",)),
    ("backends", ("allocation", "verification", "workflow", "graph", "pipeline")),
])
def test_layer_dependencies(layer, forbidden):
    for path in (ROOT / "v1" / layer).rglob("*.py"):
        for target in imports(path):
            assert not any(target == "v1." + name or target.startswith("v1." + name + ".") for name in forbidden), (path, target)


def test_runner_imports():
    for path in ROOT.glob("run*.py"):
        assert "v1.pipeline" not in imports(path)


def test_no_module_is_imported_by_string():
    """A runtime lookup is invisible to test_layer_dependencies, so ban it.

    Hiding a layer edge behind ``import_module("v1.…")`` turns the dependency
    graph green without removing the dependency, which is worse than a plain
    violation: the rule then only forbids the honest spelling.
    """

    offenders = []
    for path in (ROOT / "v1").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if not isinstance(node, ast.Call):
                continue
            if ast.unparse(node.func) in {"import_module", "importlib.import_module", "__import__"}:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} {ast.unparse(node)}")
    assert not offenders


@pytest.mark.parametrize("first", [
    "v1.backends", "v1.verification", "v1.verification.vco",
    "v1.evaluation.scalar", "v1.evaluation", "v1.pipeline",
])
def test_fresh_import_order(first):
    code = (
        f"import importlib; importlib.import_module({first!r}); "
        "from v1.allocation import *; from v1.backends import *; "
        "from v1.verification import *; import v1.workflow.vco"
    )
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True, capture_output=True)


ALL_MODULES = sorted(
    ".".join(path.relative_to(ROOT).with_suffix("").parts).removesuffix(".__init__")
    for path in (ROOT / "v1").rglob("*.py")
)


@pytest.mark.parametrize("module", ALL_MODULES)
def test_every_module_is_a_valid_entry_point(module):
    """A package __init__ cycle only shows up when its submodule imports first."""

    subprocess.run(
        [sys.executable, "-c", f"import {module}"], cwd=ROOT, check=True, capture_output=True
    )


def observed_calls(operation):
    """Observe canonical implementations at runtime, including imported aliases."""
    calls = []
    codes = {system.evaluate_system.__code__: "system", vco.measure_vco_behavior.__code__: "block"}
    def observe(frame, event, arg):
        if event == "call" and frame.f_code in codes:
            calls.append((codes[frame.f_code], frame.f_locals["vco"]))
    previous = sys.getprofile()
    sys.setprofile(observe)
    try:
        result = operation()
    finally:
        sys.setprofile(previous)
    return result, calls


def test_forward_service_uses_canonical_system_and_block_evaluators():
    from v1.allocation.service import allocate_system_spec
    from v1.api.allocation import SpecAllocationRequest
    case = load_case(ROOT / "v1/cases/vco_mapping_01.json")
    spec = SystemSpec.from_dict(case["system_spec"])
    context = {"vctrl_min_v": 0.1, "vctrl_max_v": 1.1, "temperature_points_c": [25.0], "vdd_v": 1.8}
    request = SpecAllocationRequest(spec, VCOParams(), context, {
        **case["allocation"], "initial_block_spec": case["initial_vco_requirement"],
    })
    frozen = deepcopy(request.to_dict())
    report, calls = observed_calls(lambda: allocate_system_spec(request))
    assert report["allocated"]
    assert {kind for kind, instance in calls} == {"block", "system"}
    assert report["evidence"]["boundary"]["search_knob_boundary"] == pytest.approx(-116.358121, abs=1e-6)
    assert request.to_dict() == frozen


def test_v15_and_v10_verification_share_evaluators_and_same_instance():
    from v1.allocation.design_space import DesignPointDefinition
    from v1.allocation.multidim_evaluator import evaluate_design_point
    case = load_case(ROOT / "v1/cases/vco_multidim_01.json")
    spec = SystemSpec.from_dict(case["system_spec"])
    point = DesignPointDefinition("test-point", 0, {"pn_anchor_1mhz_dbc_hz": -120.0, "k1_hz_per_v": 1e9})
    record, calls = observed_calls(lambda: evaluate_design_point(case, spec, VCOParams(), point))
    assert [kind for kind, instance in calls] == ["block", "system"]
    instance = calls[0][1]
    assert calls[1][1] is instance
    assert record["status"]["jointly_feasible"]
    request = VerificationRequest(spec, VCORequirement(-110), instance, case["block_context"])
    report, repeated = observed_calls(lambda: verify_block_assignment(request))
    assert [kind for kind, item in repeated] == ["block", "system"]
    assert all(item is instance for kind, item in repeated)
    assert report["system_tb"]["metrics"] == record["system_tb"]["metrics"]


def test_adapters_measure_without_judging():
    """BlockTB adapters observe behavior; only the service may judge it."""

    from v1.backends.synthetic import SyntheticVCOBackend, SyntheticVCOConstraintBackend
    from v1.evaluation.constraints import BEHAVIOR_VECTOR_FIELDS
    case = load_case(ROOT / "v1/cases/vco_multidim_01.json")
    spec = SystemSpec.from_dict(case["system_spec"])
    instance = VCOParams()
    cases = (
        (SyntheticVCOBackend(), VerificationRequest(spec, VCORequirement(-110.0), instance, case["block_context"])),
        (SyntheticVCOConstraintBackend(), VerificationRequest(
            spec, {"kind": "constraint_set", "constraints": list(case["block_constraints"])},
            instance, case["block_context"], backend_id="synthetic_vco_v1_constraint_set")),
    )
    for backend, request in cases:
        observation = backend.measure_block(request)
        assert not {"passed", "checks", "requirement", "residuals", "verdict"} & observation.keys()
        assert observation["measurement_method"] and observation["worst_case"]
    vector = cases[1][0].measure_block(cases[1][1])["behavior_vector"]
    assert set(vector) == set(BEHAVIOR_VECTOR_FIELDS)


def test_judgment_follows_the_injected_backend_not_the_request_label():
    """An injected adapter and the applied judgment can never disagree."""

    from v1.backends.synthetic import SyntheticVCOConstraintBackend
    case = load_case(ROOT / "v1/cases/vco_multidim_01.json")
    spec = SystemSpec.from_dict(case["system_spec"])
    request = VerificationRequest(
        spec, {"kind": "constraint_set", "constraints": list(case["block_constraints"])},
        VCOParams(), case["block_context"])
    report = verify_block_assignment(request, backend=SyntheticVCOConstraintBackend())
    assert set(report["block_tb"]["checks"]) == {
        str(item["constraint_id"]) for item in case["block_constraints"]
    }
    assert report["provenance"]["backend"] == SyntheticVCOConstraintBackend.backend_id


def test_measurement_can_be_judged_twice_without_resimulation():
    from v1.verification.vco import check_vco_spec, validate_vco_spec
    case = load_case(ROOT / "v1/cases/vco_multidim_01.json")
    spec = SystemSpec.from_dict(case["system_spec"])
    instance = VCOParams()
    measurement = vco.measure_vco_behavior(spec, instance, case["block_context"])
    frozen = deepcopy(measurement)
    assert not {"passed", "checks", "requirement"} & measurement.keys()
    pn = measurement["worst_case"]["worst_phase_noise_1mhz_dbc_hz"]
    requirement = VCORequirement(pn)
    passed, calls = observed_calls(lambda: check_vco_spec(spec, requirement, measurement))
    failed = check_vco_spec(spec, replace(requirement, phase_noise_1mhz_max_dbc_hz=pn - 1), measurement)
    assert not calls
    assert passed["checks"]["phase_noise_1mhz"]
    assert not failed["checks"]["phase_noise_1mhz"]
    assert measurement == frozen
    assert passed == validate_vco_spec(spec, requirement, instance, case["block_context"])


def test_facade_reexports_canonical_implementations():
    import v1.pipeline as facade
    from v1.evaluation.scalar import search_required_pn_boundary
    from v1.verification.vco import validate_vco_spec
    assert facade.evaluate_system is system.evaluate_system
    assert facade.measure_vco_behavior is vco.measure_vco_behavior
    assert facade.search_required_pn_boundary is search_required_pn_boundary
    assert facade.validate_vco_spec is validate_vco_spec
