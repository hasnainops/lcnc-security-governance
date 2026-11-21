"""Saved datasource references must reach sanitized query evidence."""
from copy import deepcopy
import json

import pytest

import appsmith_discovery as discovery
from test_lo1_connector_policy import stored_datasource


def action():
    return {
        "id": "query-one", "pluginType": "API", "pluginId": "rest-plugin",
        "datasource": {"id": "saved-one"},
        "actionConfiguration": {
            "path": "/private?token=SECRET", "httpMethod": "GET",
            "headers": [{"key": "Authorization", "value": "SECRET"}],
        },
        "dynamicBindingPathList": [],
    }


def collect(monkeypatch, actions, sources):
    monkeypatch.setattr(discovery, "_get_page_data", lambda *_: {"layouts": []})
    monkeypatch.setattr(discovery, "_get_page_actions", lambda *_: actions)
    observed, refs = [], []
    discovery.collect_workflow_security_metadata(
        None, {"pages": [{"id": "page-one"}], "workspaceId": "workspace-one"},
        observed, refs, workspace_datasources=sources,
    )
    return observed, refs


def test_collection_joins_references_without_leaking_or_mutating(monkeypatch):
    source = stored_datasource()
    source.update(workspaceId="workspace-one", pluginId="rest-plugin")
    queries = [action(), {**action(), "id": "query-two"}]
    before = deepcopy((queries, source))
    observed, refs = collect(monkeypatch, queries, [source])
    assert len(observed) == 2
    for item in observed:
        assert item["destination_state"] == "observed"
        assert item["destination"] == {"scheme": "https", "host": "example.com"}
    assert {item["datasource_id"] for item in refs} == {"saved-one"}
    assert (queries, source) == before
    assert not any(value in json.dumps(observed) for value in ("SECRET", "secret", "private"))


@pytest.mark.parametrize("path", ["", "/", "v1/items", "/v1/items?limit=2"])
def test_static_relative_paths_resolve(monkeypatch, path):
    query = action()
    query["actionConfiguration"]["path"] = path
    observed, _ = collect(monkeypatch, [query], [stored_datasource()])
    assert observed[0]["destination_state"] == "observed"


@pytest.mark.parametrize("path", [
    "{{host}}", "/{{path}}", "https://other.example/", "//other.example/",
    "\\\\other.example", None, [], "http://[bad",
])
def test_dynamic_or_absolute_paths_remain_unresolved(monkeypatch, path):
    query = action()
    query["actionConfiguration"]["path"] = path
    observed, _ = collect(monkeypatch, [query], [stored_datasource()])
    assert observed[0]["destination_state"] == "unresolved"


@pytest.mark.parametrize("case", [
    "missing_reference", "failed_enumeration", "wrong_plugin", "wrong_workspace",
    "multiple_environments", "dynamic_saved_host", "dynamic_embedded_host",
    "conflicting_embedded_host", "path_binding", "datasource_binding",
])
def test_uncertain_reference_is_not_promoted(monkeypatch, case):
    query, source = action(), stored_datasource()
    sources = [source]
    if case == "missing_reference":
        query["datasource"]["id"] = "missing"
    elif case == "failed_enumeration":
        sources = None
    elif case == "wrong_plugin":
        source["pluginId"] = "different-plugin"
    elif case == "wrong_workspace":
        query["workspaceId"] = "different-workspace"
        source["workspaceId"] = "workspace-one"
    elif case == "multiple_environments":
        source["datasourceStorages"]["another"] = deepcopy(source["datasourceStorages"]["unused_env"])
    elif case == "dynamic_saved_host":
        source["datasourceStorages"]["unused_env"]["datasourceConfiguration"]["url"] = "https://{{host}}"
    elif case in {"dynamic_embedded_host", "conflicting_embedded_host"}:
        query["datasource"]["datasourceConfiguration"] = {
            "url": "https://{{host}}" if case == "dynamic_embedded_host" else "https://different.example",
        }
    else:
        key = "actionConfiguration.path" if case == "path_binding" else "datasource.url"
        query["dynamicBindingPathList"] = [{"key": key}]
    observed, _ = collect(monkeypatch, [query], sources)
    assert observed[0]["destination_state"] == "unresolved"
    assert "destination" not in observed[0]


def test_duplicate_saved_identity_rejected(monkeypatch):
    with pytest.raises(RuntimeError, match="Duplicate datasource identity"):
        collect(monkeypatch, [action()], [stored_datasource(), stored_datasource()])


def test_cross_workspace_enumeration_rejected(monkeypatch):
    source = stored_datasource()
    source["workspaceId"] = "different-workspace"
    with pytest.raises(RuntimeError, match="workspace mismatch"):
        collect(monkeypatch, [action()], [source])


def test_inline_action_keeps_own_destination(monkeypatch):
    query = action()
    query["datasource"] = {"datasourceConfiguration": {"url": "https://inline.example"}}
    observed, _ = collect(monkeypatch, [query], [])
    assert observed[0]["destination"]["host"] == "inline.example"


@pytest.mark.parametrize("empty", [None, {}])
def test_empty_reference_configuration_can_use_saved_source(monkeypatch, empty):
    query = action()
    query["datasource"]["datasourceConfiguration"] = empty
    query["datasource"]["datasourceStorages"] = empty
    observed, _ = collect(monkeypatch, [query], [stored_datasource()])
    assert observed[0]["destination_state"] == "observed"


def test_join_removes_only_evidence_warning_and_changes_classification_hash(monkeypatch):
    from lo1_classification_support import modules, sources

    inputs = modules(monkeypatch).classification_inputs
    app, context, row, now = sources()
    source, query = stored_datasource(), action()
    reconciliation = discovery.reconcile_action_datasources(
        [source], [{"action_id": query["id"], "datasource_id": source["id"]}],
    )
    row["payload"]["connectors"] = discovery.build_verified_saved_connector_evidence([source], reconciliation)
    row["payload"]["observed_actions"] = [discovery._sanitize_action_observation(query)]
    before = inputs.build_classification_inputs(app, context, row, now)
    row["payload"]["observed_actions"], _ = collect(monkeypatch, [query], [source])
    after = inputs.build_classification_inputs(app, context, row, now)
    assert "integration_destinations_unresolved" in before.review_reasons
    assert "integration_destinations_unresolved" not in after.review_reasons
    assert set(after.review_reasons) == set(before.review_reasons) - {"integration_destinations_unresolved"}
    assert after.semantic_hash != before.semantic_hash
    assert after.payload == before.payload  # No model prompt/threshold manipulation.


def test_unresolved_query_still_requires_review(monkeypatch):
    from lo1_classification_support import modules, sources

    inputs = modules(monkeypatch).classification_inputs
    app, context, row, now = sources()
    query = action()
    query["actionConfiguration"]["path"] = "{{runtime_path}}"
    row["payload"]["observed_actions"], _ = collect(monkeypatch, [query], [stored_datasource()])
    result = inputs.build_classification_inputs(app, context, row, now)
    assert "integration_destinations_unresolved" in result.review_reasons


def test_inline_api_with_empty_storages_records_origin(monkeypatch):
    query = action()
    query["datasource"] = {
        "datasourceConfiguration": {"url": "http://governance-api:8000"},
        "datasourceStorages": {},
    }
    query["actionConfiguration"]["path"] = "/applications/{{appsmith.store.currentApplicationId}}/history"
    observed, refs = collect(monkeypatch, [query], [])
    assert observed[0]["destination"] == {"scheme": "http", "host": "governance-api", "port": 8000}
    assert refs[0]["datasource_id"] is None
