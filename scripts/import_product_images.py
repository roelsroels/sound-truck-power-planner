"""Prepare small, same-origin product previews from official manufacturer imagery.

Run offline during catalogue maintenance, never in the request path. Requires
Pillow (already in requirements.txt) and curl. Raw responses stay in work/.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urljoin, urlparse
from PIL import Image, ImageOps
try:
    from .import_manufacturers import Page, Importer
    from .funktion_one import load_documents, rich
except ImportError:
    from import_manufacturers import Page, Importer
    from funktion_one import load_documents, rich

HOSTS={'www.bcspeakers.com','bcspeakers.com','www.powersoft.com','funktion-one.com',
       'funktion-one.cdn.prismic.io','images.prismic.io','prismic-io.s3.amazonaws.com'}
Image.MAX_IMAGE_PIXELS=25_000_000


class Fetcher:
    def __init__(self,cache):
        self.cache=Path(cache);self.cache.mkdir(parents=True,exist_ok=True)
    def fetch(self,url):
        p=urlparse(url)
        if p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password or p.port not in (None,443):
            raise ValueError('Unexpected image/page origin: '+url)
        file=self.cache/(sha256(url.encode()).hexdigest()+'.bin')
        if not file.exists():
            temporary=file.with_suffix('.part')
            time.sleep(.12)
            try:
                subprocess.run(['curl','--fail','--silent','--show-error','--proto','=https','--max-redirs','0',
                                '--connect-timeout','8','--max-time','25','--max-filesize','8000000',
                                '--user-agent','SoundPowerPlanner/1.0 product preview importer',url,'-o',str(temporary)],check=True,capture_output=True)
                if temporary.stat().st_size>8_000_000:raise ValueError('Image/page exceeds size cap')
                temporary.replace(file)
            finally:
                temporary.unlink(missing_ok=True)
        return file.read_bytes()


def image_source(product,content,fo_documents):
    """Select product photos only: no graphs, drawings, logos or guessed URLs."""
    brand=product['manufacturer_id']
    if brand=='funktion-one':
        record,_=fo_documents[urlparse(product['source_url']).path]
        data=record['data'];url=data.get('overviewImage',{}).get('url') or data.get('featuredImage',{}).get('url')
        if record['type']=='product-system':
            url=next((s.get('primary',{}).get('image',{}).get('url') for s in data.get('slices',[]) if s['slice_type']=='featured_image'),None)
        return url, product['model']!=rich(data.get('pageTitle')) or record['type']=='product-system'
    if brand=='bc-speakers':
        match=re.search(r'window\.__remixContext = (.*?);</script>',content,re.S)
        if not match:raise ValueError('B&C page structure changed')
        data=json.loads(match[1])['state']['loaderData'];record=list(data.values())[-1]['product']
        photos=[p for p in record.get('images',[]) if p.get('path') and p['path'].startswith('uploads/products/images/')]
        photos.sort(key=lambda p: 'front' not in p['path'].lower())
        return ('https://bcspeakers.com/'+photos[0]['path'] if photos else None),False
    if brand=='powersoft':
        for record in Page(content).jsonld:
            if record.get('@type')!='Product':continue
            value=record.get('image')
            if isinstance(value,list):value=value[0] if value else None
            if isinstance(value,dict):value=value.get('url') or value.get('contentUrl')
            return (urljoin(product['source_url'],value) if value else None),product['model']!=(record.get('model') or record.get('name'))
    return None,False


def thumbnail(raw):
    with Image.open(BytesIO(raw)) as original:
        original.load()
        image=ImageOps.exif_transpose(original).convert('RGBA')
        image.thumbnail((720,480),Image.Resampling.LANCZOS)
        background=Image.new('RGB',image.size,'#f5f5f2');background.paste(image,mask=image.getchannel('A'))
        out=BytesIO();background.save(out,'WEBP',quality=82,method=6)
        return out.getvalue(),image.size


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',default='work/product-image-cache')
    parser.add_argument('--manufacturer-cache',default='work/manufacturer-cache')
    parser.add_argument('--packs',default='app/library_data')
    parser.add_argument('--output',default='web/library-images')
    args=parser.parse_args();fetcher=Fetcher(args.cache);out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    packs={file:json.loads(file.read_text()) for file in sorted(Path(args.packs).glob('*.json'))}
    fo_documents=load_documents(Importer(args.manufacturer_cache))
    groups={}
    for pack in packs.values():
        for p in pack['products']:
            key=(p['manufacturer_id'],p['model'] if p['manufacturer_id']=='bc-speakers' else p['source_url'])
            groups.setdefault(key,[]).append(p)
    unavailable=[]
    def prepare(group):
        first=group[0]
        try:
            content='' if first['manufacturer_id']=='funktion-one' else fetcher.fetch(first['source_url']).decode()
            url,_=image_source(first,content,fo_documents)
            if not url:raise ValueError('No published product photograph')
            raw=fetcher.fetch(url);encoded,(width,height)=thumbnail(raw)
            asset=sha256(encoded).hexdigest()[:24]+'.webp'
            (out/asset).write_bytes(encoded)
            for p in group:
                _,representative=image_source(p,content,fo_documents)
                p['image']={'asset':asset,'source_url':url,'representative':representative,'width':width,'height':height}
            return len(group)
        except Exception as error:
            for p in group:p.pop('image',None)
            unavailable.append({'products':[p['id'] for p in group],'reason':str(error),'source':first['source_url']})
            print('Image unavailable:',first['model'],str(error)[:130],flush=True)
            return 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        counts=[]
        for i,count in enumerate(pool.map(prepare,groups.values()),1):
            counts.append(count)
            if i%25==0:print('Prepared',i,'of',len(groups),'photo groups',flush=True)
    for file,pack in packs.items():file.write_text(json.dumps(pack,ensure_ascii=False,indent=2)+'\n')
    used={p['image']['asset'] for pack in packs.values() for p in pack['products'] if p.get('image')}
    for file in out.glob('*.webp'):
        if file.name not in used:file.unlink()
    report={'products_with_images':sum(counts),'unique_images':len(used),'image_bytes':sum((out/f).stat().st_size for f in used),'unavailable':unavailable}
    Path(args.cache,'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='unavailable'}),flush=True)


if __name__=='__main__':main()
