from pathlib import Path


ROOT = Path(__file__).parent.parent


def test_apps_page_does_not_redeclare_shared_app_state():
    shared_script = (ROOT / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    apps_page = (ROOT / "web" / "apps.html").read_text(encoding="utf-8")

    assert "let allApps" in shared_script
    assert "let allApps" not in apps_page
