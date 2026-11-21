"""LO4 Governance API forwarding to authenticated JIT checks."""

from uuid import UUID

from app import access


APP_ID = UUID("12c59ac4-4f59-4a47-ac7c-a8e528e52c42")

SUBJECT = "vault:a84be332-d855-42cb-a442-419509c5d26f"


def test_jit_check_forwards_bearer_credential(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"active": False, "grant": None}

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(
        access.httpx, "get", fake_get
    )

    request = access.AccessRequest(
        subject_id=SUBJECT,
        role="developer",
        action="export",
    )

    result = access.check_jit_privilege(
        APP_ID,
        request,
        authorization="Bearer isolated-test-token",
    )

    assert result["active"] is False
    assert len(calls) == 1

    url, kwargs = calls[0]

    assert url.endswith("/privileges/check")
    assert kwargs["headers"] == {
        "Authorization": "Bearer isolated-test-token"
    }
    assert kwargs["params"]["subject_id"] == SUBJECT


def test_missing_bearer_not_fabricated(monkeypatch):
    captured = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"active": False, "grant": None}

    def fake_get(url, **kwargs):
        captured.append(kwargs)
        return FakeResponse()

    monkeypatch.setattr(
        access.httpx, "get", fake_get
    )

    request = access.AccessRequest(
        subject_id=SUBJECT,
        role="developer",
        action="read",
    )

    access.check_jit_privilege(
        APP_ID, request, authorization=None
    )

    assert captured[0]["headers"] == {}
