from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_index_hides_component_shell_until_bootstrap_is_ready():
    source = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert 'class="app-loading"' in source
    assert "html.app-loading .container" in source
    assert 'id="appBoot"' in source
    assert 'src="app/app.js?v=17"' in source
    assert "initializeComponents" not in source


def test_component_styles_start_loading_from_document_head():
    source = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    expected = (
        "header.css",
        "sidebar.css",
        "section-dashboard.css",
        "section-accounts.css",
        "section-playground.css",
        "section-usage-stats.css",
        "section-logs.css",
        "section-api-keys.css",
        "section-gems.css",
        "section-settings.css",
    )
    for stylesheet in expected:
        assert f'components/{stylesheet}' in source


def test_bootstrap_has_one_initialization_path_and_reveals_after_init():
    source = (ROOT / "static" / "app" / "app.js").read_text(encoding="utf-8")
    assert source.count("initializeComponents()") == 1
    assert "await componentsReady" in source
    assert "await initApp()" in source
    assert "revealApp()" in source
    assert "setTimeout(async () =>" not in source


def test_component_loader_waits_for_styles_before_inserting_markup():
    source = (ROOT / "static" / "app" / "component-loader.js").read_text(encoding="utf-8")
    wait = "await Promise.all(prepared.flatMap(component => component.styles));"
    insert = "prepared.forEach(component => {"
    assert wait in source
    assert source.index(wait) < source.index(insert)


def test_account_oauth_browser_flow_keeps_manual_token_fallback():
    markup = (ROOT / "static" / "components" / "section-accounts.html").read_text(encoding="utf-8")
    source = (ROOT / "static" / "app" / "app.js").read_text(encoding="utf-8")
    oauth_source = (ROOT / "static" / "app" / "gemini-oauth.js").read_text(encoding="utf-8")

    for element_id in (
        "add-oauth-generate",
        "add-oauth-auth-url",
        "add-oauth-code",
        "add-oauth-exchange",
        "update-oauth-generate",
        "update-oauth-code",
        "update-oauth-exchange",
        "add-oauth-manual-fields",
        "update-oauth-manual-fields",
    ):
        assert f'id="{element_id}"' in markup

    assert "/admin/gemini/oauth/auth-url" in oauth_source
    assert "/admin/gemini/oauth/exchange-code" in oauth_source
    assert "isOAuthAuthorized('add')" in source
    assert "isOAuthAuthorized('update')" in source
    assert "function createOAuthFlowState" not in source
    assert "function createOAuthFlowState" in oauth_source
    assert 'id="add-access-token"' in markup
    assert 'id="add-refresh-token"' in markup
