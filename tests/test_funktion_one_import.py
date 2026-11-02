"""Offline importer regression checks; never contact manufacturer services in CI."""
from copy import deepcopy
from scripts.funktion_one import parse_record, merge_aliases


def record(uid='f61'):
    return {'type':'product','uid':uid,'data':{
        'pageTitle':[{'text':'F61'}],
        'overviewText':[{'text':'Use with the self-powered SB8A.'}],
        'technicalTable':[{'driver':'6 inch','power':'500W','nominalImpedence':'8Ω'}],
        'secondaryTechnicalTable':[{'weight':'6kg','connectors':'NL4'}],
        'downloads':[{'downloadFile':{'url':'https://funktion-one.cdn.prismic.io/spec.pdf'}}]}}


def test_powered_companion_and_audio_watts_never_create_mains_consumption():
    p=parse_record(record(),'compact-range','2026-11-02')
    assert p['kind']=='passive_cabinet' and p['power_input']=='none'
    assert p['electrical'] is None
    assert next(s['value'] for s in p['specs'] if s['label']=='Power (AES)')=='500W'
    assert next(s['value'] for s in p['specs'] if s['label']=='Weight')=='6kg'
    assert p['datasheet_urls']==['https://funktion-one.cdn.prismic.io/spec.pdf']


def test_explicit_powered_model_keeps_consumption_unknown():
    p=parse_record(record('res-2a'),'heritage','2026-11-02')
    assert p['kind']=='active_cabinet' and p['power_input']=='ac'
    assert p['status']=='archived' and p['electrical'] is None


def test_alias_merge_keeps_distinct_values_and_source_conditions():
    p=parse_record(record(),'compact-range','2026-11-02');other=deepcopy(p)
    other.update(category='public-address',source_url='https://funktion-one.com/product/f61-pa/')
    other['specs'][0]['value']='Alternative driver label'
    merged=merge_aliases([p,other])
    assert len(merged)==1
    specs=merged[0]['specs']
    assert len({s['key'] for s in specs})==len(specs)
    assert any(s['value']=='Alternative driver label' and s['notes']==other['source_url'] for s in specs)
    assert merged[0]['electrical'] is None
