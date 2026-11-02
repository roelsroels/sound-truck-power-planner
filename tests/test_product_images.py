"""Offline photo selection must never substitute a plot or generic site logo."""
from io import BytesIO
import json
from PIL import Image
from scripts.import_product_images import image_source, thumbnail, Fetcher
import pytest


def test_photo_selection_uses_manufacturer_product_fields():
    bc = {'manufacturer_id':'bc-speakers'}
    record = {'state':{'loaderData':{'product':{'product':{'images':[
        {'path':'uploads/products/graphs/frequency.jpg'},
        {'path':'uploads/products/images/rear.jpg'},
        {'path':'uploads/products/images/front.jpg'},
    ]}}}}}
    page = '<script>window.__remixContext = '+json.dumps(record)+';</script>'
    assert image_source(bc,page,{}) == ('https://bcspeakers.com/uploads/products/images/front.jpg',False)
    power = {'manufacturer_id':'powersoft','source_url':'https://www.powersoft.com/family','model':'Variant'}
    assert image_source(power,'<meta property="og:image" content="logo.png">',{}) == (None,False)
    page = '<script type="application/ld+json">'+json.dumps({'@type':'Product','name':'Family','image':'/photo.webp'})+'</script>'
    assert image_source(power,page,{}) == ('https://www.powersoft.com/photo.webp',True)


def test_thumbnail_contains_extreme_aspect_ratios_without_upscaling():
    for size in [(2000,100),(100,2000),(40,40)]:
        raw=BytesIO();Image.new('RGBA',size,(0,0,0,0)).save(raw,'PNG')
        encoded,dimensions=thumbnail(raw.getvalue())
        with Image.open(BytesIO(encoded)) as photo:
            assert photo.format == 'WEBP' and photo.size == dimensions
            assert photo.width <= min(720,size[0]) and photo.height <= min(480,size[1])
            assert abs(photo.width/photo.height-size[0]/size[1]) < .01


def test_image_fetcher_rejects_unapproved_origins_before_network(tmp_path):
    for url in ['http://www.powersoft.com/photo','https://127.0.0.1/photo','https://www.powersoft.com@localhost/photo']:
        with pytest.raises(ValueError):Fetcher(tmp_path).fetch(url)
