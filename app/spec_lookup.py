"""Small, guarded manufacturer page inspector.

There is no general-purpose URL fetcher: only explicitly supported HTTPS hostnames
and product paths. Findings are candidates for human review, never generator loads.
"""
from html.parser import HTMLParser
from ipaddress import ip_address
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import json
import re
import socket
import time
from pathlib import Path

INDEX = Path(__file__).with_name("spec_index.json")
HOSTS = {"www.bcspeakers.com", "bcspeakers.com", "www.powersoft.com", "powersoft.com"}
_CACHE = {}
_ACTIVITY = {}
_LOCK = Lock()

class _Words(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.words = []
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script","style","noscript"):
            self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ("script","style","noscript"):
            self.hidden = max(0, self.hidden-1)
        if tag in ("div","p","tr","h1","h2","h3","h4","li","br","td"):
            self.words.append(" ")
    def handle_data(self, data):
        if not self.hidden:
            self.words.append(data + " ")

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def search_models(model):
    query = " ".join(model.lower().split())
    if not 2 <= len(query) <= 100:
        raise ValueError("Enter between 2 and 100 characters")
    data = json.loads(INDEX.read_text())
    tokens = query.split()
    matched = [item for item in data if all(token in
               (item["model"]+" "+item["manufacturer"]+" "+item["description"]).lower()
               for token in tokens)]
    return matched[:15]

def allowed_url(url):
    if not isinstance(url,str) or len(url)>750:
        raise ValueError("Invalid source URL")
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname not in HOSTS or parts.port not in (None,443)
            or parts.username or parts.password or parts.fragment
            or not parts.path.startswith("/en/products/")):
        raise ValueError("Only official HTTPS manufacturer product pages are accepted")
    # Guard against accidental private-address DNS results.
    for result in socket.getaddrinfo(parts.hostname,443,type=socket.SOCK_STREAM):
        addr = ip_address(result[4][0])
        if not addr.is_global:
            raise ValueError("Manufacturer host did not resolve to a public address")
    return parts.geturl()

def _fetch(url):
    opener = build_opener(NoRedirect())
    req = Request(url, headers={"User-Agent":"SoundTruckPlanner/2.0 (+product-spec-inspection)",
                                "Accept":"text/html"})
    with opener.open(req, timeout=6) as response:
        if response.status != 200:
            raise ValueError("Manufacturer returned an unexpected status")
        if "text/html" not in response.headers.get("Content-Type","").lower():
            raise ValueError("Page is not HTML; PDF parsing is not supported")
        content = response.read(200001)
        if len(content)>200000:
            raise ValueError("Manufacturer page exceeds the size limit")
        return content.decode("utf-8","replace")

def inspect(url):
    url = allowed_url(url)
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(url)
        if cached and now-cached[0]<600:
            return cached[1]
    try:
        document = _fetch(url)
    except (OSError, HTTPError, URLError) as exc:
        raise ValueError("The official page could not be reached") from exc
    parser = _Words()
    parser.feed(document)
    cleaned = re.sub(r"\s+"," ","".join(parser.words)).strip()
    if len(cleaned)<90:
        raise ValueError("No readable specification text found")
    fields = {}
    patterns = {
        "impedance_ohm":r"Nominal Impedance\s*(\d+(?:[.,]\d+)?)\s*(?:Ω|Ohm)",
        "nominal_driver_w":r"Nominal Power Handling\s*(\d+(?:[.,]\d+)?)\s*W",
        "continuous_program_w":r"Continuous Power Handling\s*(\d+(?:[.,]\d+)?)\s*W",
        "nominal_diameter_mm":r"Nominal Diameter\s*(\d+(?:[.,]\d+)?)\s*mm",
        "weight_kg":r"Net Weight\s*(\d+(?:[.,]\d+)?)\s*kg",
    }
    for key,pattern in patterns.items():
        found=re.search(pattern,cleaned,re.I)
        if found:
            fields[key]=float(found.group(1).replace(",","."))
    # Do not conflate 1/8-power amplifier mains VA with continuous consumption.
    snippets=[]
    for pattern in (r"power consumption",r"1/8 of max output",r"nominal power requirement",
                    r"nominal power handling",r"output power"):
        hit=re.search(pattern,cleaned,re.I)
        if hit:
            snippets.append(cleaned[max(0,hit.start()-35):min(len(cleaned),hit.start()+170)])
    result={"url":url,"manufacturer":"B&C Speakers" if "bcspeakers" in url else "Powersoft",
            "fields":fields,"evidence":snippets[:5],
            "warning":"Unreviewed manufacturer text. Driver audio watts are NOT amplifier AC mains demand. Verify datasheet model, load and test condition before applying any value."}
    with _LOCK:
        if len(_CACHE)>64:
            _CACHE.clear()
        _CACHE[url]=(now,result)
    return result

def rate_limit(client):
    now = time.monotonic()
    key=client or "unknown"
    with _LOCK:
        recent=[t for t in _ACTIVITY.get(key,[]) if now-t<60]
        if len(recent)>=4:
            raise ValueError("Manufacturer lookup limit reached; retry later")
        recent.append(now)
        if len(_ACTIVITY)>500: _ACTIVITY.clear()
        _ACTIVITY[key]=recent
