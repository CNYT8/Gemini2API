"""Shared Gemini model catalog aligned with Sub2API's Gemini platform."""

DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"
DEFAULT_GEM_MODEL = "gemini-2.5-pro"

# Keep the order in sync with sub2api/backend/internal/pkg/geminicli/models.go.
GEMINI_MODEL_CATALOG = (
    ("gemini-2.0-flash", "Gemini 2.0 Flash"),
    ("gemini-2.5-flash", "Gemini 2.5 Flash"),
    ("gemini-2.5-flash-image", "Gemini 2.5 Flash Image"),
    ("gemini-2.5-pro", "Gemini 2.5 Pro"),
    ("gemini-3.5-flash", "Gemini 3.5 Flash"),
    ("gemini-3-flash-preview", "Gemini 3 Flash Preview"),
    ("gemini-3-pro-preview", "Gemini 3 Pro Preview"),
    ("gemini-3.1-pro-preview", "Gemini 3.1 Pro Preview"),
    ("gemini-3.1-flash-image", "Gemini 3.1 Flash Image"),
)

# Sub2API exposes this Code Assist route through the native Gemini model API,
# while keeping it out of the shorter admin/test selector.
GEMINI_NATIVE_EXTRA_MODELS = (
    ("gemini-3.1-pro-preview-customtools", "Gemini 3.1 Pro Preview Custom Tools"),
)

PUBLIC_MODELS = [model_id for model_id, _ in GEMINI_MODEL_CATALOG]
NATIVE_MODELS = [
    *PUBLIC_MODELS[:-1],
    GEMINI_NATIVE_EXTRA_MODELS[0][0],
    PUBLIC_MODELS[-1],
]
MODEL_DISPLAY_NAMES = dict(GEMINI_MODEL_CATALOG + GEMINI_NATIVE_EXTRA_MODELS)

LEGACY_CATALOG_ALIASES = {
    "gemini-pro": "gemini-2.5-pro",
    "gemini-flash": "gemini-2.0-flash",
    "gemini-flash-thinking": "gemini-3-flash-preview",
    "gemini-2.5-flash-thinking": "gemini-3-flash-preview",
    "gemini-2.5-pro-preview-05-06": "gemini-2.5-pro",
    "gemini-2.5-flash-preview-04-17": "gemini-2.5-flash",
    "gemini-2.5-flash-preview-05-20": "gemini-2.5-flash",
    "gemini-2.0-flash-thinking": "gemini-3-flash-preview",
    "gemini-2.0-flash-lite": "gemini-2.0-flash",
    "gemini-1.5-pro": "gemini-2.5-pro",
    "gemini-1.5-flash": "gemini-2.0-flash",
}


def normalize_model_name(model: str) -> str:
    """Normalize native ``models/`` identifiers to the shared bare model ID."""
    return (model or "").strip().removeprefix("models/")


def normalize_catalog_model(model: str) -> str:
    """Map a legacy public model name to its current catalog counterpart."""
    normalized = normalize_model_name(model)
    return LEGACY_CATALOG_ALIASES.get(normalized, normalized)
