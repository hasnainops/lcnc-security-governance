import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

MODULE_PATH = (
    ROOT
    / "discovery"
    / "appsmith_discovery.py"
)

spec = importlib.util.spec_from_file_location(
    "appsmith_workflow_observer_test",
    MODULE_PATH,
)

discovery = importlib.util.module_from_spec(
    spec
)

spec.loader.exec_module(discovery)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def get(
        self,
        url,
        params=None,
    ):
        if "/api/v1/pages/" in url:
            return FakeResponse(
                {
                    "responseMeta": {"success": True},
                    "data": {
                        "layouts": [
                            {
                                "dsl": {
                                    "children": [
                                        {},
                                        {},
                                        {},
                                    ]
                                }
                            }
                        ]
                    }
                }
            )

        if url.endswith("/api/v1/actions"):
            return FakeResponse(
                {
                    "responseMeta": {"success": True},
                    "data": [
                        {
                            "pluginType": "API",
                            "isValid": True,
                            "dynamicBindingPathList": [
                                {},
                                {},
                            ],
                            "actionConfiguration": {
                                "httpMethod": "POST",
                                "headers": [
                                    {
                                        "key": "Authorization",
                                        "value": "SECRET-VALUE",
                                    }
                                ],
                            },
                            "datasource": {
                                "datasourceConfiguration": {
                                    "url": (
                                        "http://internal.example"
                                    )
                                }
                            },
                        },
                        {
                            "pluginType": "API",
                            "isValid": False,
                            "dynamicBindingPathList": [],
                            "actionConfiguration": {
                                "httpMethod": "GET",
                                "headers": [],
                            },
                            "datasource": {
                                "datasourceConfiguration": {
                                    "url": (
                                        "https://secure.example"
                                    )
                                }
                            },
                        },
                    ]
                }
            )

        raise AssertionError(
            f"Unexpected URL: {url}"
        )


def test_collects_only_sanitized_workflow_security_counts():
    application = {
        "pages": [
            {
                "id": "page-1",
            }
        ]
    }

    result = (
        discovery
        .collect_workflow_security_metadata(
            FakeClient(),
            application,
        )
    )

    assert result == {
        "page_count": 1,
        "widget_count": 3,
        "action_count": 2,
        "api_action_count": 2,
        "dynamic_binding_count": 2,
        "invalid_action_count": 1,
        "http_action_count": 1,
        "https_action_count": 1,
        "sensitive_header_action_count": 1,
    }

    serialized = str(result)

    assert "SECRET-VALUE" not in serialized
    assert "internal.example" not in serialized
    assert "secure.example" not in serialized


@pytest.mark.parametrize(
    "getter,payload",
    [
        ("_get_page_data", None),
        ("_get_page_data", []),
        ("_get_page_data", {}),
        ("_get_page_data", {"data": None}),
        ("_get_page_data", {"data": []}),
        ("_get_page_data", {"data": {}}),
        ("_get_page_actions", {}),
        ("_get_page_actions", {"data": None}),
        ("_get_page_actions", {"data": {}}),
        ("_get_page_actions", {"data": "SECRET-VALUE"}),
        ("_get_page_actions", {"data": [None]}),
        ("_get_page_actions", {"data": ["SECRET-VALUE"]}),
        (
            "_get_page_data",
            {
                "responseMeta": {"success": False},
                "data": {"layouts": []},
            },
        ),
        (
            "_get_page_actions",
            {
                "responseMeta": {
                    "success": False,
                    "error": "SECRET-VALUE",
                },
                "data": [],
            },
        ),
        (
            "_get_page_actions",
            {"responseMeta": None, "data": []},
        ),
        (
            "_get_page_actions",
            {"responseMeta": {}, "data": []},
        ),
    ],
)
def test_rejects_malformed_observation_responses(getter, payload):
    class Client:
        def get(self, url, params=None):
            return FakeResponse(payload)

    with pytest.raises(
        RuntimeError,
        match="Invalid Appsmith observation response",
    ) as caught:
        getattr(discovery, getter)(Client(), "page-1")

    assert "SECRET-VALUE" not in str(caught.value)


@pytest.mark.parametrize(
    "payload,accepted",
    [
        ({"data": []}, False),
        ({"responseMeta": {"success": True}, "data": []}, True),
    ],
)
def test_empty_action_list_requires_valid_response_meta(
    payload, accepted
):
    class Client:
        def get(self, url, params=None):
            return FakeResponse(payload)

    if accepted:
        assert discovery._get_page_actions(
            Client(), "page-1"
        ) == []
    else:
        with pytest.raises(
            RuntimeError,
            match="Invalid Appsmith observation response",
        ):
            discovery._get_page_actions(
                Client(), "page-1"
            )


def test_incomplete_actions_abort_workflow_observation():
    class IncompleteClient(FakeClient):
        def get(self, url, params=None):
            if url.endswith("/api/v1/actions"):
                return FakeResponse({})
            return super().get(url, params=params)

    with pytest.raises(
        RuntimeError,
        match="Invalid Appsmith observation response",
    ):
        discovery.collect_workflow_security_metadata(
            IncompleteClient(),
            {"pages": [{"id": "page-1"}]},
        )
