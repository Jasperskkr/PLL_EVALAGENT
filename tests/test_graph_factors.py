from v1.graph import Factor, TypedGraph, add_factor_to_graph, audit_factor_graph, factor_view


def _graph_with_refs() -> TypedGraph:
    graph = TypedGraph(
        "factor-test",
        graph_version="2.0",
        metadata={
            "semantic_role_model": [
                "architecture",
                "behavior",
                "influence",
                "evidence",
            ]
        },
    )
    graph.add_node("SystemSpec", "system_requirement", {"source": "test"})
    graph.add_node("k1", "design_variable", {}, semantic_role="behavior")
    graph.add_node("x2", "design_variable", {}, semantic_role="behavior")
    graph.add_node("Context", "context", {}, semantic_role="architecture")
    graph.add_node("BlockRequirement", "block_requirement", {"source": "test"})
    return graph


def test_factor_schema_supports_arbitrary_input_refs():
    factor = Factor.from_dict(
        {
            "factor_id": "future_3d",
            "factor_type": "allocation",
            "name": "future",
            "inputs": ["SystemSpec", "k1", "x2", "Context"],
            "outputs": ["BlockRequirement"],
            "model_kind": "piecewise_linear",
        }
    )
    assert factor.input_refs == ("SystemSpec", "k1", "x2", "Context")


def test_factor_projection_and_audit_are_canonical_graph_views():
    graph = _graph_with_refs()
    add_factor_to_graph(
        graph,
        Factor(
            factor_id="future_3d",
            factor_type="allocation",
            name="future",
            input_refs=("SystemSpec", "k1", "x2", "Context"),
            output_refs=("BlockRequirement",),
            model_kind="piecewise_linear",
        ),
        status="validated",
    )
    artifact = graph.to_dict()
    audit = audit_factor_graph(artifact, required_factor_ids=("future_3d",))
    projection = factor_view(artifact)
    assert audit["passed"] is True
    assert projection["factors"][0]["inputs"] == [
        "SystemSpec",
        "k1",
        "x2",
        "Context",
    ]
    assert projection["metadata"]["read_only"] is True
