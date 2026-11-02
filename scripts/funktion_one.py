"""Offline adapter for Funktion-One's published ranges and technical fields.

Official range HTML and its public CMS JSON are parsed as data. No remote JavaScript is evaluated and no
speaker/amplifier audio ratings are treated as AC consumption.
"""
from copy import deepcopy
import json
from pathlib import Path
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlparse, urlencode

HOST = 'https://funktion-one.com'
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}


class Node:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def text(self):
        return re.sub(r'\s+', ' ', ' '.join(c.text() if isinstance(c, Node) else c for c in self.children)).strip()

    def nodes(self, tag=None, cls=None):
        for child in self.children:
            if not isinstance(child, Node): continue
            if (tag is None or child.tag == tag) and (cls is None or cls in child.attrs.get('class','').split()):
                yield child
            yield from child.nodes(tag, cls)


class Document(HTMLParser):
    def __init__(self, content):
        super().__init__(); self.root = Node(); self.stack = [self.root]; self.feed(content)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.stack[-1]); self.stack[-1].children.append(node)
        if tag not in VOID: self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID: self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]; break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def slug(value):
    return re.sub('[^a-z0-9]+','-',value.lower()).strip('-')


def links(doc):
    for a in doc.root.nodes('a'):
        u = urlparse(urljoin(HOST, a.attrs.get('href','')))
        if u.hostname == 'funktion-one.com' and u.scheme == 'https':
            yield u.path.rstrip('/')+'/', a.text()


API = 'https://funktion-one.cdn.prismic.io/api/v2'


def rich(value):
    if isinstance(value,str): return value.strip()
    return '\n'.join(v.get('text','') for v in value or [] if isinstance(v,dict)).strip()


def load_documents(importer):
    metadata=json.loads(importer.fetch(API))
    ref=next(r['ref'] for r in metadata['refs'] if r.get('isMasterRef'))
    url=API+'/documents/search?'+urlencode({'ref':ref,'q':'[[any(document.type,["product","accessory","product-system"])]]','pageSize':100,'page':1})
    records={}
    while url:
        page=json.loads(importer.fetch(url))
        for record in page['results']:
            prefix={'product':'product','accessory':'accessories','product-system':'product-system'}[record['type']]
            records['/'+prefix+'/'+record['uid']+'/']=(record,importer.checked_at(url))
        url=page['next_page']
        if url and not url.startswith(API+'/documents/search?'): raise ValueError('Unexpected CMS pagination URL')
    return records


def parse_record(record,category,checked_at):
    data=record['data']; model=rich(data['pageTitle'])
    if not model: raise ValueError('Missing model: '+record['uid'])
    specs=[]; documents=set()
    def add(section,label,value,notes=''):
        if value: specs.append({'key':'published.'+str(len(specs)),'section':section,'label':label,'value':str(value).strip(),'notes':notes})
    labels={'driver':'Driver','operatingBand':'Operating band','sensitivity':'Sensitivity at 1m','power':'Power (AES)',
            'nominalImpedence':'Nominal impedance','frequencyResponse':'Usable bandwidth (-3dB)','weight':'Weight',
            'dispersion':'Nominal dispersion','connectors':'Connectors'}
    for i,row in enumerate(data.get('technicalTable',[])):
        for key,value in row.items(): add('Driver '+row.get('driver',str(i+1)),labels.get(key,key),value)
    for row in data.get('secondaryTechnicalTable',[]):
        for key,value in row.items(): add('Cabinet',labels.get(key,key),value)
    if record['type']=='accessory':
        add('Accessory','Application / compatibility',rich(data.get('accessoryName')))
        compatible=[p['product'].get('uid','') for p in data.get('compatibleProducts',[])]
        add('Accessory','Compatible products',', '.join(filter(None,compatible)))
    # Read structured technical sections only; do not copy overview/marketing prose.
    for section in data.get('slices',[]):
        if section['slice_type']=='list_section':
            for item in section['items']: add('Published specifications',rich(item.get('label')),rich(item.get('value')))
        elif section['slice_type']=='accordion_section':
            for item in section['items']:
                if rich(item.get('label')).upper()!='ADDITIONAL INFORMATION': continue
                context='Additional information'
                for paragraph in item.get('text',[]):
                    text=paragraph.get('text','').strip()
                    if not text: continue
                    if text.endswith(':') or (text.isupper() and len(text)<60): context='Additional information / '+text.rstrip(':'); continue
                    label,sep,value=text.partition(':')
                    add(context,label.strip() if sep else 'Published technical note',value.strip() if sep else text)
        image=section.get('primary',{}).get('image',{}).get('url','')
        # Public image tables remain available as source documents, never copied as assets.
        if image and any(t in image.lower() for t in ('output','table','performance','performancfeature','technicaldrawing','technical-drawing')):
            documents.add(image)
    for download in data.get('downloads',[]):
        url=download.get('downloadFile',{}).get('url')
        if url: documents.add(url)
    for field in ('technicalDrawing','dimensionsImage','comparisonImage'):
        url=data.get(field,{}).get('url')
        if url: documents.add(url)
    kind='passive_cabinet'; power='none'
    if record['type']=='accessory' or record['uid']=='infrahorn': kind='accessory'
    if record['type']=='product-system':
        kind='amplifier' if record['uid'] in ('d-series','f-series','e-series1','tourrack') else 'accessory'
        power='ac' if kind=='amplifier' else 'unknown'
    # "Active" multi-way/bi-amped speakers still require an external amplifier.
    # Optional powered versions mentioned on passive pages do not change the base model.
    if record['uid'] in ('res-2a','f221a','sb210a'): kind='active_cabinet';power='ac'
    if not specs: add('Documentation','Technical data','See the linked official technical tables and documents; no tabulated text values are published.')
    prefix={'product':'product','accessory':'accessories','product-system':'product-system'}[record['type']]
    return {'id':'funktion-one-'+slug(model),'manufacturer_id':'funktion-one','model':model,'variant':'',
            'kind':kind,'category':category,'power_input':power,'status':'archived' if category=='heritage' else 'current',
            'source_url':HOST+'/'+prefix+'/'+record['uid']+'/', 'datasheet_urls':sorted(documents),
            'checked_at':checked_at,'specs':specs,'electrical':None}


def merge_aliases(products):
    merged={}
    for p in products:
        if p['id'] not in merged: merged[p['id']]=p;continue
        old=merged[p['id']]
        if (old['kind'],old['status'])!=(p['kind'],p['status']): raise ValueError('Conflicting model aliases: '+p['id'])
        seen={(s['section'],s['label'],s['value']) for s in old['specs']}
        for spec in p['specs']:
            if (spec['section'],spec['label'],spec['value']) in seen: continue
            old['specs'].append({**spec,'key':'alias.'+str(len(old['specs'])),'section':spec['section']+' / '+p['category'],'notes':p['source_url']})
        old['specs'].append({'key':'range.'+p['category'],'section':'Range listings','label':'Also listed in','value':p['category'],'notes':p['source_url']})
        old['datasheet_urls']=sorted(set(old['datasheet_urls']+p['datasheet_urls']))
    return list(merged.values())


def collect(importer):
    root=Document(importer.fetch(HOST+'/ranges/'))
    pending={path for path,_ in links(root) if path.startswith(('/ranges/','/product-system/')) and path!='/ranges/'}
    pending.add('/accessories/');visited=set();listed={}
    while pending:
        path=min(pending);pending.remove(path)
        if path in visited: continue
        visited.add(path)
        if path=='/product-system/software/': continue
        doc=Document(importer.fetch(HOST+path));category=path.strip('/').split('/')[-1]
        for link,text in links(doc):
            if text=='Product Information':
                if link.startswith('/accessories/'): listed.setdefault(link,'accessories')
                elif link.startswith(('/product/','/product-system/')):
                    if link not in listed or category=='heritage': listed[link]='electronics' if path.startswith('/product-system/') else category
            elif link.startswith('/ranges/') and link!='/ranges/' and link not in visited: pending.add(link)
    if len(listed)<80: raise ValueError('Funktion-One range discovery appears incomplete')
    docs=load_documents(importer);missing=set(listed)-set(docs)
    if missing: raise ValueError('No official structured record for: '+', '.join(sorted(missing)))
    products=merge_aliases([parse_record(docs[path][0],category,docs[path][1]) for path,category in sorted(listed.items())])
    # Add reviewed model-specific tables and explicitly documented powered variants.
    supplements=json.loads(Path(__file__).with_name('funktion_one_supplements.json').read_text())
    by_id={p['id']:p for p in products}
    for family,table in supplements['amplifiers'].items():
        base=by_id['funktion-one-'+family]
        if table['source_url'] not in base['datasheet_urls']: raise ValueError('Amplifier table changed; review transcription: '+family)
        for model,rows in table['models'].items():
            product=deepcopy(base);product.update(id='funktion-one-'+slug(model),model=model)
            product['specs']=[{**s,'section':'Family documentation / '+s['section'],'notes':'Family-level data; DSP properties apply only to DSP-equipped models. '+s['notes']} for s in product['specs'] if not (s['section'].endswith('Weight') or s['label'] in table['models'])]
            for label,value in rows.items():
                product['specs'].append({'key':'model.'+slug(label),'section':'Selected model','label':label,'value':value,'notes':table['notes']+' Source: '+table['source_url']})
            products.append(product)
    for model,source_model in [('SB8A','SB8'),('SB10A','SB10')]:
        base=by_id['funktion-one-'+slug(source_model)]
        record=docs[urlparse(base['source_url']).path][0];text=rich(record['data'].get('overviewText'))
        if not re.search(r'self[- ]powered '+model+r'\b',text,re.I): raise ValueError('Powered variant source changed: '+model)
        product=deepcopy(base);product.update(id='funktion-one-'+slug(model),model=model,kind='active_cabinet',power_input='ac')
        product['specs']=[{'key':'variant.channels','section':'Powered variant','label':'Amplifier channels','value':'3; satellite outputs','notes':''},
                          {'key':'variant.supply','section':'Powered variant','label':'Power supply','value':'100–240V universal','notes':'Consumption is not published as VA.'},
                          {'key':'variant.path','section':'Powered variant','label':'Signal path','value':'Analogue','notes':'Passive cabinet weight/connectors have not been copied to the powered variant.'}]
        products.append(product)
    print('Funktion-One:',len(listed),'official listings;',len(products),'unique model/variant records',flush=True)
    return {'id':'funktion-one','name':'Funktion-One','website':HOST},products
