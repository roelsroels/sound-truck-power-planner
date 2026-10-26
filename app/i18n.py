"""Small shared English/Dutch message catalogue; report language is request-local."""
import json
import re
from contextvars import ContextVar
from pathlib import Path

LANGUAGE = ContextVar('report_language', default='en')
MESSAGES = json.loads((Path(__file__).resolve().parent.parent / 'web' / 'nl.json').read_text())
PATTERNS = []
for source, target in MESSAGES.items():
    slots = re.findall(r'\{(\d+)\}', source)
    if slots:
        pattern = '(.*?)'.join(re.escape(part) for part in re.split(r'\{\d+\}', source))
        PATTERNS.append((len(re.sub(r'\{\d+\}', '', source)), re.compile('^'+pattern+'$', re.S), slots, target))
PATTERNS.sort(key=lambda item:item[0], reverse=True)


def translate(value, depth=0):
    if LANGUAGE.get() != 'nl' or not isinstance(value, str):
        return value
    if value in MESSAGES:
        return MESSAGES[value]
    if depth > 3:
        return value
    for _, pattern, slots, target in PATTERNS:
        match = pattern.fullmatch(value)
        if match:
            values = {slot: translate(match.group(i+1), depth+1) for i, slot in enumerate(slots)}
            return re.sub(r'\{(\d+)\}', lambda m: values[m.group(1)], target)
    return value
