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
        assert c.get("/api/v2/specs/search",params={"model":" B&C 12NDL88 "}).json()["items"][0]["model"]=="12NDL88"
        assert c.get("/api/v2/specs/search",params={"model":"does-not-exist"}).json()=={"items":[]}
        for model in ("", "a", "x"*101):
            assert c.get("/api/v2/specs/search",params={"model":model}).status_code==422
        assert c.post("/api/v2/specs/inspect",json={"url":"https://example.com/en/products/foo"}).status_code in (422,502)


def test_v2_pdf_appendix(tmp_path):
    with TestClient(create_app(str(tmp_path/"pdf.sqlite3"), admin_token="")) as c:
        project=c.get("/api/v1/example").json()
        equipment=c.get("/api/v1/catalog").json()
        project["meter_summary"]={
            "kind":"measured-ac-real-power","average_kw":12.5,"observed_peak_kw":16,
            "energy_kwh":6.25,"minutes":30,"samples":61,"largest_gap_min":1
        }
        project["generator_fuel_curve"]={
            "model":"Generic 40 kVA prime set","source":"supplier datasheet",
            "p25":3.1,"p50":5.2,"p75":7.3,"p100":9.6
        }
        project["circuit_notes"]={"0":{"length_m":15,"breaker_a":32,"cable_mm2":6,"engineer_reviewed":False}}
        response=c.post("/api/v1/reports/engineering.pdf",json={"project":project,"equipment":equipment})
        assert response.status_code==200
        assert response.content.startswith(b"%PDF-")
        assert len(response.content)>6000
        assert b"/Type /Page" in response.content
