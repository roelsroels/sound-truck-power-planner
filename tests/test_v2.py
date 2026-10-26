from app import spec_lookup
from fastapi.testclient import TestClient
from app.main import create_app
import pytest

def test_indexed_official_models():
    hits=spec_lookup.search_models("12NDL88")
    assert len(hits)>=1
    assert hits[0]["manufacturer"]=="B&C Speakers"
    assert "bcspeakers.com" in hits[0]["url"]
    assert spec_lookup.search_models("does-not-exist")==[]

def test_guarded_url_rejection():
    for url in [
        "http://www.powersoft.com/en/products/amp-modules/m-drive",
        "https://127.0.0.1/en/products/amp-modules/m-drive",
        "https://www.powersoft.com.evil.example/en/products/amp-modules/m-drive",
        "https://www.powersoft.com@127.0.0.1/en/products/amp-modules/m-drive",
        "https://www.powersoft.com/internal",
    ]:
        with pytest.raises(ValueError):
            spec_lookup.allowed_url(url)

def test_page_extraction_with_fixture(monkeypatch):
    monkeypatch.setattr(spec_lookup,"allowed_url",lambda url:url)
    monkeypatch.setattr(spec_lookup,"_fetch",lambda url:"""
    <html><body><h1>12NDL88</h1><p>Nominal Diameter 320 mm</p>
    <p>Nominal Impedance 8 Ω</p><p>Nominal Power Handling 700 W</p>
    <p>Continuous Power Handling 1400 W</p><p>Net Weight 4.95 kg</p>
    </body></html>
    """)
    result=spec_lookup.inspect("https://www.bcspeakers.com/en/products/lf-driver/12/8/12NDL88")
    assert result["fields"]["nominal_driver_w"]==700
    assert result["fields"]["impedance_ohm"]==8
    assert result["fields"]["weight_kg"]==4.95
    assert "NOT amplifier AC" in result["warning"]

def test_v2_search_and_read_only_api(tmp_path):
    with TestClient(create_app(str(tmp_path/"v2.sqlite3"),admin_token="")) as c:
        r=c.get("/api/v2/specs/search",params={"model":"M-Drive"})
        assert r.status_code==200
        assert any("M-Drive"==x["model"] for x in r.json()["items"])
        assert c.get("/api/v2/specs/search",params={"model":"a"}).status_code==422
        assert c.post("/api/v2/specs/inspect",json={"url":"https://example.com/en/products/foo"}).status_code in (422,502)
