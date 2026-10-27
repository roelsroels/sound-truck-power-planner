"""Import public technical facts from official B&C/Powersoft product pages.

Run from the repository root. No scraping runs in the web application.
Only structured specifications are imported; images and marketing copy are not.
Add other manufacturers as version-1 JSON packs (see docs/library.md).
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class Page(HTMLParser):
    def __init__(self, content):
        super().__init__(); self.links = []; self.jsonld = []; self.tables = []; self._table = None; self._row = None; self._cell = None; self._link = None; self._script = None
        self.feed(content)
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'table': self._table = []
        if tag == 'tr' and self._table is not None: self._row = []
        if tag in ('td','th') and self._row is not None: self._cell = ''
        if tag == 'br' and self._cell is not None: self._cell += ' / '
        if tag == 'a': self._link = [attrs.get('href', ''), '']
        if tag == 'script' and attrs.get('type') == 'application/ld+json': self._script = ''
    def handle_data(self, data):
        if self._cell is not None: self._cell += data
        if self._link is not None: self._link[1] += data
        if self._script is not None: self._script += data
    def handle_endtag(self, tag):
        if tag in ('td','th') and self._cell is not None:
            self._row.append(self._cell.strip()); self._cell = None
        if tag == 'tr' and self._row is not None:
            self._table.append(self._row); self._row = None
        if tag == 'table' and self._table is not None:
            self.tables.append(self._table); self._table = None
        if tag == 'a' and self._link is not None: self.links.append(tuple(self._link)); self._link = None
        if tag == 'script' and self._script is not None:
            self.jsonld.append(json.loads(self._script)); self._script = None


def plain(value):
    if value is None: return ''
    if isinstance(value, dict):
        if 'value' in value: return plain(value['value'])
        return ' / '.join(f'{plain(v)} {k}' for k, v in value.items() if v is not None and not k.startswith('_'))
    if isinstance(value, list): return ' / '.join(map(plain, value))
    return unescape(re.sub('<[^>]+>', '', str(value))).strip()


def slug(value):
    return re.sub('[^a-z0-9]+', '-', str(value).lower()).strip('-')


class Importer:
    def __init__(self, cache):
        self.cache = Path(cache); self.cache.mkdir(parents=True, exist_ok=True)
    def fetch(self, url):
        if urlparse(url).hostname not in ('www.bcspeakers.com', 'www.powersoft.com'):
            raise ValueError('Unexpected manufacturer host')
        file = self.cache / (sha256(url.encode()).hexdigest() + '.html')
        if file.exists(): return file.read_text()
        for attempt in range(3):
            try:
                time.sleep(.15)
                with urlopen(Request(url, headers={'User-Agent': 'SoundPowerPlanner/1.0 public technical catalogue importer'}), timeout=35) as response:
                    content = response.read(12_000_000).decode()
                file.write_text(content); return content
            except Exception:
                if attempt == 2: raise
                time.sleep(1 + attempt)
    def checked_at(self, url):
        file = self.cache / (sha256(url.encode()).hexdigest() + '.html')
        return datetime.fromtimestamp(file.stat().st_mtime, timezone.utc).date().isoformat()
    def bc(self):
        host = 'https://www.bcspeakers.com'
        def loader(content):
            match = re.search(r'window\.__remixContext = (.*?);</script>', content, re.S)
            if not match: raise ValueError('B&C page structure changed')
            return json.loads(match[1])['state']['loaderData']
        root = loader(self.fetch(host + '/en'))['root']
        urls = set()
        for category in root['productCategories']:
            cat = category['_id']
            for path in (f'/en/products/{cat}', f'/en/products/archive/{cat}'):
                page = Page(self.fetch(host + path))
                found = {urljoin(host, u) for u, _ in page.links if re.match(r'^/en/products/(?:archive/)?' + re.escape(cat) + r'/(?:archive/)?[^/]+/[^/]+/[^/]+$', u)}
                urls.update(found)
                print('B&C', path, len(found), flush=True)
        def product(url):
            content = self.fetch(url); data = list(loader(content).values())[-1]['product']
            specs = []
            for section in ('generalSpecs','lfSpecs','mfSpecs','hfSpecs','hornSpecs','crossOverSpecs','params','design','shippingMounting'):
                for key, field in (data.get(section) or {}).items():
                    if not isinstance(field, dict): continue
                    value = field.get('computedValue') or plain(field.get('value')) or plain(field.get('content'))
                    if value:
                        label = field.get('label') or re.sub(r'(?<!^)([A-Z])', r' \1', key).capitalize()
                        specs.append({'key': section + '.' + key, 'section': section, 'label': label, 'value': plain(value), 'notes': plain(field.get('notes'))})
                note = plain(data.get(section + 'Notes'))
                if note: specs.append({'key': section + '.notes', 'section': section, 'label': 'Notes', 'value': note, 'notes': ''})
            page = Page(content)
            docs = sorted({urljoin(host, u) for u, _ in page.links if '.pdf' in u.lower()})
            cat = data['category']['_id']
            return {'id': 'bc-speakers-' + data['id'], 'manufacturer_id': 'bc-speakers', 'model': data['name'],
                    'variant': plain(data.get('nominalImpedance')) + ' Ω' if data.get('nominalImpedance') else '',
                    'kind': 'accessory' if cat in ('horn', 'crossovers') else 'driver', 'category': cat,
                    'status': 'archived' if data.get('archived') or data.get('noLongerInProduction') else 'current',
                    'source_url': url, 'datasheet_urls': docs, 'checked_at': self.checked_at(url), 'specs': specs, 'electrical': None, 'power_input': 'none'}
        with ThreadPoolExecutor(max_workers=3) as pool: products = list(pool.map(product, sorted(urls)))
        return {'id': 'bc-speakers', 'name': 'B&C Speakers', 'website': host}, products
    def powersoft(self):
        host = 'https://www.powersoft.com'
        page = Page(self.fetch(host + '/en/products'))
        pattern = r'^/en/products/(?:amp-modules|transducers|install-amps|touring-amps|pocket-sized-amps|onboard-amps|onboard-amplifiers)/[^#?]+$'
        roots = {u for u, _ in page.links if re.match(pattern, u)}
        initial_roots = set(roots)
        for archive in ('/en/discontinued-products','/en/eol'):
            roots.update(u for u, _ in Page(self.fetch(host + archive)).links if re.match(pattern, u))
        archived = (roots - initial_roots) | {u for u, text in page.links if re.match(pattern, u) and re.search('Discontinued|End of Life', text, re.I)}
        pages = {}
        for root in sorted(roots):
            content = self.fetch(host + root); pages[root] = content
            children = {u for u, _ in Page(content).links if u.startswith(root + '/') and re.match(pattern, u)}
            for child in sorted(children): pages[child] = self.fetch(host + child)
            print('Powersoft', root, len(children), flush=True)
        products = {}
        for path, content in sorted(pages.items(), key=lambda x: len(x[0])):
            page = Page(content)
            for data in page.jsonld:
                if data.get('@type') != 'Product': continue
                model = data.get('model') or data['name']
                specs = []
                for i, prop in enumerate(data.get('additionalProperty', [])):
                    label = prop.get('name', '')
                    section, _, detail = label.partition(': ')
                    specs.append({'key': 'published.' + str(i), 'section': section if detail else 'Specifications', 'label': detail or label, 'value': plain(prop.get('value')), 'notes': ''})
                for table_index, table in enumerate(page.tables):
                    for row_index, row in enumerate(table):
                        if len(row) > 1 and row[0] and any(row[1:]):
                            specs.append({'key': f'table.{table_index}.{row_index}', 'section': 'Published table ' + str(table_index + 1), 'label': row[0], 'value': ' | '.join(row[1:]), 'notes': ''})
                # Do not invent specifications if the manufacturer publishes none.
                docs = sorted({urljoin(host, u) for u, _ in page.links if '.pdf' in u.lower()})
                kind = 'driver' if '/transducers/' in path else 'amplifier'
                electrical = None
                for prop in data.get('additionalProperty', []):
                    if re.search('^Power consumption', prop.get('name', ''), re.I) and re.fullmatch(r'[0-9.]+ VA', plain(prop.get('value'))):
                        electrical = {'reference_va': float(plain(prop['value']).split()[0]), 'design_va': None, 'power_factor': None, 'basis': prop['name'] + ': ' + plain(prop['value'])}
                was_archived = products.get(slug(model), {}).get('status') == 'archived'
                products[slug(model)] = {'id': 'powersoft-' + slug(model), 'manufacturer_id': 'powersoft', 'model': model,
                    'variant': '', 'kind': kind, 'category': path.split('/')[3],
                    'status': 'archived' if was_archived or any(path == a or path.startswith(a + '/') for a in archived) else 'current',
                    'source_url': host + path, 'datasheet_urls': docs, 'checked_at': self.checked_at(host + path), 'specs': specs, 'electrical': electrical,
                    'power_input': 'none' if kind == 'driver' else 'dc' if 'onboard' in path or model == 'NOTA 142' else 'ac'}
        for key, product in list(products.items()):
            if product['model'] not in ('UNICA', 'UNICA T'): continue
            page = Page(pages[urlparse(product['source_url']).path])
            for table in page.tables:
                if not table or table[0][0] != 'Model': continue
                for row in table[1:]:
                    if not re.fullmatch(r'[0-9]+[KM][0-9]+', row[0], re.I): continue
                    model = product['model'] + ' ' + row[0]
                    selected = [{'key': 'selected.' + str(i), 'section': 'Selected model', 'label': table[0][i], 'value': row[i], 'notes': ''} for i in range(1, min(len(row),len(table[0])))]
                    products[slug(model)] = {**product, 'id': 'powersoft-' + slug(model), 'model': model, 'specs': selected + product['specs']}
            del products[key]
        return {'id': 'powersoft', 'name': 'Powersoft', 'website': host}, [p for p in products.values() if p['specs']]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', default='work/manufacturer-cache')
    parser.add_argument('--output', default='app/library_data')
    parser.add_argument('--manufacturer', choices=['bc', 'powersoft', 'all'], default='all')
    args = parser.parse_args(); importer = Importer(args.cache); out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    for name in (['bc','powersoft'] if args.manufacturer == 'all' else [args.manufacturer]):
        manufacturer, products = getattr(importer, name)()
        if not products or len({p['id'] for p in products}) != len(products): raise ValueError('Empty or duplicate catalogue')
        # Separate small category packs keep reviews and repository tools manageable.
        for old in out.glob(manufacturer['id'] + '-*.json'):
            old.unlink()
        for category in sorted({p['category'] for p in products}):
            selected = sorted((p for p in products if p['category'] == category), key=lambda p: p['id'])
            for offset in range(0, len(selected), 40):
                pack = {'schema_version': 1, 'manufacturers': [manufacturer], 'products': selected[offset:offset+40]}
                suffix = '-' + str(offset // 40 + 1) if len(selected) > 40 else ''
                (out / f'{manufacturer["id"]}-{slug(category)}{suffix}.json').write_text(json.dumps(pack, ensure_ascii=False, indent=2) + '\n')
        print(manufacturer['name'], len(products), 'variants imported', flush=True)


if __name__ == '__main__': main()
