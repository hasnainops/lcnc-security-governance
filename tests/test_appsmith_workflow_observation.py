import importlib.util
from pathlib import Path


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
