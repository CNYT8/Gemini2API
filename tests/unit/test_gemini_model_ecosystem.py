from app.core.gemini_client import _resolve_model
from app.core.gemini_models import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GEM_MODEL,
    DEFAULT_IMAGE_MODEL,
    NATIVE_MODELS,
    PUBLIC_MODELS,
    normalize_catalog_model,
    normalize_model_name,
)
from app.core.gemini_oauth_client import _oauth_model_name


SUB2API_GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-image",
    "gemini-2.5-pro",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-3-pro-preview",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-image",
]


def test_public_catalog_matches_sub2api_gemini_cli_catalog():
    assert PUBLIC_MODELS == SUB2API_GEMINI_MODELS
    assert NATIVE_MODELS == [
        *SUB2API_GEMINI_MODELS[:-1],
        "gemini-3.1-pro-preview-customtools",
        SUB2API_GEMINI_MODELS[-1],
    ]


def test_defaults_match_sub2api_roles():
    assert DEFAULT_GEMINI_MODEL == "gemini-2.0-flash"
    assert DEFAULT_IMAGE_MODEL == "gemini-2.5-flash-image"
    assert DEFAULT_GEM_MODEL == "gemini-2.5-pro"


def test_cookie_models_resolve_by_web_family():
    family_models = {
        "pro": "gemini-3-pro-plus",
        "flash": "gemini-3-flash-plus",
        "flash-thinking": "gemini-3-flash-thinking-plus",
    }
    assert _resolve_model("gemini-2.5-pro", family_models) == "gemini-3-pro-plus"
    assert _resolve_model("gemini-3.1-pro-preview", family_models) == "gemini-3-pro-plus"
    assert _resolve_model("gemini-2.5-flash-image", family_models) == "gemini-3-flash-plus"
    assert _resolve_model("models/gemini-3.5-flash", family_models) == "gemini-3-flash-plus"


def test_oauth_models_pass_through_and_legacy_names_remain_compatible():
    assert _oauth_model_name("models/gemini-3.1-pro-preview") == "gemini-3.1-pro-preview"
    assert _oauth_model_name("gemini-2.5-flash-image") == "gemini-2.5-flash-image"
    assert _oauth_model_name("gemini-pro") == "gemini-3-pro-preview"
    assert normalize_model_name("models/gemini-2.0-flash") == "gemini-2.0-flash"
    assert normalize_catalog_model("gemini-pro") == "gemini-2.5-pro"
    assert normalize_catalog_model("models/gemini-flash") == "gemini-2.0-flash"


def test_native_models_endpoint_uses_google_wire_field_names(gem_client):
    auth = {"Authorization": "Bearer sk-test-key"}
    response = gem_client.get("/v1beta/models", headers=auth)
    assert response.status_code == 200
    models = response.json()["models"]
    assert [item["name"].removeprefix("models/") for item in models] == NATIVE_MODELS
    assert all("displayName" in item for item in models)
    assert all("supportedGenerationMethods" in item for item in models)
    assert all("display_name" not in item for item in models)


def test_native_model_detail_matches_catalog(gem_client):
    auth = {"Authorization": "Bearer sk-test-key"}
    response = gem_client.get("/v1beta/models/gemini-3.1-pro-preview", headers=auth)
    assert response.status_code == 200
    assert response.json()["name"] == "models/gemini-3.1-pro-preview"

    missing = gem_client.get("/v1beta/models/not-a-gemini-model", headers=auth)
    assert missing.status_code == 404
    assert missing.json()["error"]["status"] == "NOT_FOUND"


def test_legacy_model_whitelist_maps_to_current_catalog(gem_client, monkeypatch):
    import app.routers.gemini as gemini_router

    auth = {"Authorization": "Bearer sk-test-key"}
    monkeypatch.setattr(gemini_router.settings, "model_whitelist", "gemini-pro")
    response = gem_client.get("/v1beta/models", headers=auth)
    assert response.status_code == 200
    assert [item["name"] for item in response.json()["models"]] == [
        "models/gemini-2.5-pro"
    ]
