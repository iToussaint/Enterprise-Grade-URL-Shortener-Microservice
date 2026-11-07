import json
import re
from typing import Any

import jsonschema
import pytest
from fakeredis import FakeRedis
from flask.testing import FlaskClient

LONG_URL = "https://www.example.com/articles/2026/flask-guide"


@pytest.fixture
def spec(client: FlaskClient) -> dict[str, Any]:
    response = client.get("/api/swagger.json")
    assert response.json is not None
    spec: dict[str, Any] = response.json
    return spec


def assert_matches_definition(spec: dict[str, Any], definition: str, body: Any) -> None:
    # Validate a real response body against the schema Swagger publishes.
    schema = {
        "$ref": f"#/definitions/{definition}",
        "definitions": spec["definitions"],
    }
    jsonschema.validate(body, schema)


def test_create_short_url_returns_201_with_location(
    client: FlaskClient, redis_client: FakeRedis
) -> None:
    response = client.post("/api/urls", json={"url": LONG_URL})

    assert response.status_code == 201
    body = response.json
    assert body is not None
    short_code = body["short_code"]
    assert len(short_code) == 7
    assert body["short_url"] == f"http://localhost/api/{short_code}"
    assert body["original_url"] == LONG_URL
    assert response.headers["Location"] == body["short_url"]
    assert redis_client.get(f"url:{short_code}") == LONG_URL


def test_create_short_url_stores_normalized_url(client: FlaskClient) -> None:
    response = client.post("/api/urls", json={"url": "https://Example.COM"})

    assert response.status_code == 201
    assert response.json is not None
    assert response.json["original_url"] == "https://example.com/"


def test_redirect_returns_302_to_original_url(client: FlaskClient) -> None:
    created = client.post("/api/urls", json={"url": LONG_URL})
    assert created.json is not None

    response = client.get(f"/api/{created.json['short_code']}")

    assert response.status_code == 302
    assert response.headers["Location"] == LONG_URL


def test_redirect_unknown_code_returns_404_json(client: FlaskClient) -> None:
    response = client.get("/api/missing")

    assert response.status_code == 404
    assert response.json == {
        "error": {
            "code": "not_found",
            "message": "Short code 'missing' was not found.",
        }
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"url": "not-a-url"},
        {"url": "ftp://files.example.com/report.pdf"},
        {"url": "javascript:alert(1)"},
        {"url": ""},
        {},
    ],
)
def test_create_short_url_rejects_invalid_input_with_422(
    client: FlaskClient, payload: dict[str, str]
) -> None:
    response = client.post("/api/urls", json=payload)

    assert response.status_code == 422
    assert response.json is not None
    assert set(response.json) == {"error"}
    error = response.json["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["field"] == "url"


def test_create_short_url_rejects_non_object_body_with_422(
    client: FlaskClient,
) -> None:
    response = client.post("/api/urls", json=["https://example.com"])

    assert response.status_code == 422
    assert response.json is not None
    assert response.json["error"]["details"][0]["field"] == "body"


def test_swagger_documents_endpoints_and_schemas(client: FlaskClient) -> None:
    spec = client.get("/api/swagger.json").json
    assert spec is not None

    assert "post" in spec["paths"]["/urls"]
    assert "get" in spec["paths"]["/{short_code}"]
    assert "ShortenRequest" in spec["definitions"]
    assert "ShortenResponse" in spec["definitions"]


def test_documented_status_codes(spec: dict[str, Any]) -> None:
    create = spec["paths"]["/urls"]["post"]["responses"]
    redirect = spec["paths"]["/{short_code}"]["get"]["responses"]

    assert set(create) == {"201", "400", "415", "422", "503"}
    assert set(redirect) == {"302", "404", "503"}
    assert "Location" in create["201"]["headers"]
    assert "Location" in redirect["302"]["headers"]


def test_operations_have_summaries(spec: dict[str, Any]) -> None:
    assert spec["paths"]["/urls"]["post"]["summary"] == "Create a short URL"
    assert (
        spec["paths"]["/{short_code}"]["get"]["summary"]
        == "Redirect to the original URL"
    )


def test_all_schema_references_resolve(spec: dict[str, Any]) -> None:
    # Swagger 2.0 only understands "#/definitions/..." references.
    references = re.findall(r'"\$ref": "([^"]+)"', json.dumps(spec))

    assert references
    for reference in references:
        assert reference.startswith("#/definitions/")
        assert reference.removeprefix("#/definitions/") in spec["definitions"]


def test_created_response_matches_documented_schema(
    client: FlaskClient, spec: dict[str, Any]
) -> None:
    response = client.post("/api/urls", json={"url": LONG_URL})

    assert_matches_definition(spec, "ShortenResponse", response.json)


@pytest.mark.parametrize(
    ("method", "path", "kwargs", "status"),
    [
        ("POST", "/api/urls", {"json": {"url": "ftp://x.org"}}, 422),
        (
            "POST",
            "/api/urls",
            {"data": "{bad", "content_type": "application/json"},
            400,
        ),
        ("POST", "/api/urls", {"data": "url=x"}, 415),
        ("GET", "/api/missing", {}, 404),
    ],
)
def test_error_responses_match_documented_schema(
    client: FlaskClient,
    spec: dict[str, Any],
    method: str,
    path: str,
    kwargs: dict[str, Any],
    status: int,
) -> None:
    response = client.open(path, method=method, **kwargs)

    assert response.status_code == status
    assert_matches_definition(spec, "ErrorResponse", response.json)


def test_documented_examples_match_their_schemas(spec: dict[str, Any]) -> None:
    for name in ("ShortenRequest", "ShortenResponse", "ErrorResponse"):
        example = spec["definitions"][name]["example"]
        assert_matches_definition(spec, name, example)
