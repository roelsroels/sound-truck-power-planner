import pytest
from app.supply import venue_assessment
from app.report import build_pdf
import json
from pathlib import Path

@pytest.mark.parametrize('capacity,status', [
    ({},'unknown'), ({'L1':12.5,'L2':0,'L3':0},'covered'),
    ({'L1':12,'L2':100,'L3':100},'insufficient'),
    ({'L1':0},'insufficient'), ({'L1':20,'L2':'','L3':0},'unknown'),
])
def test_venue_phase_capacity(capacity,status):
    result=venue_assessment({'venue_supply':capacity},{'L1':2300,'L2':0,'L3':0},2300,2.3,1.25,230)
    assert result['required_a']['L1']==12.5
    assert result['required_kva']==2.875
    assert result['required_kw']==2.875
    assert result['status']==status


def test_fixed_report_includes_venue_and_fallback(monkeypatch):
    import app.report as report
    sections=[]
    original=report.section
    def record(label):
        sections.append(label)
        return original(label)
    monkeypatch.setattr(report,'section',record)
    project=json.loads(Path('app/example.json').read_text())
    equipment=json.loads(Path('app/seed.json').read_text())
    project.update(setup_mode='fixed',venue_supply={'L1':16,'L2':16,'L3':16})
    document=build_pdf(project,equipment)
    assert document.startswith(b'%PDF-')
    assert '04 / Venue requirements and generator fallback' in sections
    assert '04 / Vehicle planning' not in sections
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/fixed-engineering-report.pdf').write_bytes(document)
