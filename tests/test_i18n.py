import json
from pathlib import Path
from app.i18n import LANGUAGE, translate
from app.report import build_pdf


def test_dutch_report_and_request_isolation(monkeypatch):
    import app.report as report
    original=report.SimpleDocTemplate
    def uncompressed(*args,**kwargs):
        return original(*args,**kwargs,pageCompression=0)
    monkeypatch.setattr(report,'SimpleDocTemplate',uncompressed)
    project=json.loads(Path('app/example.json').read_text())
    equipment=json.loads(Path('app/seed.json').read_text())
    project.update(language='nl',setup_mode='fixed',venue_supply={'L1':16,'L2':16,'L3':16})
    dutch=build_pdf(project,equipment)
    assert b'BEOORDELING STROOMVOORZIENING' in dutch
    assert b'Locatievoeding' in dutch
    assert b'De locatievoeding is onvoldoende' in dutch
    assert LANGUAGE.get()=='en'
    project['language']='en'
    english=build_pdf(project,equipment)
    assert b'SUPPLY ASSESSMENT' in english
    assert b'BEOORDELING STROOMVOORZIENING' not in english
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/dutch-engineering-report.pdf').write_bytes(dutch)


def test_dutch_nested_messages():
    token=LANGUAGE.set('nl')
    try:
        assert translate('Venue assessment: Venue supply is insufficient. Arrange a generator or reduce/rebalance the load.').startswith('Beoordeling locatievoeding: De locatievoeding is onvoldoende')
        assert translate('B&C 12NDL88')=='B&C 12NDL88'
    finally:
        LANGUAGE.reset(token)


def test_dutch_pdf_accents():
    from app.report import plain
    assert plain('geïmporteerd, geïnstalleerd, één') == 'geimporteerd, geinstalleerd, een'
