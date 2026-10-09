import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings
from chennalink.app import ChennaLinkApp

def test_health_endpoints():
    """Verify both /health and /api/health respond with 200 and healthy status."""
    client = TestClient(app)
    
    r1 = client.get("/health")
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1["status"] == "healthy"
    assert data1["service"] == "fluxlink"

    r2 = client.get("/api/health")
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["status"] == "healthy"
    assert data2["service"] == "fluxlink"

def test_cors_headers_for_production_frontend():
    """Verify CORS preflight and response allows https://fluxlink.chennareddy.in."""
    client = TestClient(app)
    headers = {
        "Origin": "https://fluxlink.chennareddy.in",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    }
    res = client.options("/api/sessions/create", headers=headers)
    assert res.headers.get("access-control-allow-origin") == "https://fluxlink.chennareddy.in"

def test_cli_custom_backend_argument():
    """Verify CLI ChennaLinkApp accepts custom backend_url override."""
    app_instance = ChennaLinkApp(backend_url="https://custom.backend.com")
    assert app_instance.api_base == "https://custom.backend.com/api"
    assert app_instance.ws_base == "wss://custom.backend.com/ws"

def test_cli_help_screen_registered():
    """Verify HelpScreen is properly registered in SCREENS."""
    assert "help" in ChennaLinkApp.SCREENS
    binding_keys = [b.key for b in ChennaLinkApp.BINDINGS]
    assert "ctrl+h" in binding_keys
