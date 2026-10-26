"""Venue supply arithmetic, independent of generator power-factor assumptions."""
import math


def venue_assessment(project, phases, design_va, design_kw, headroom, voltage):
    raw = project.get('venue_supply')
    raw = raw if isinstance(raw, dict) else {}
    required = {phase: va * headroom / voltage for phase, va in phases.items()}
    available = {}
    for phase in phases:
        try:
            value = float(raw.get(phase))
            available[phase] = value if math.isfinite(value) and value >= 0 else None
        except (TypeError, ValueError):
            available[phase] = None
    short = any(available[p] is not None and available[p] < required[p] for p in phases)
    unknown = any(available[p] is None for p in phases)
    return {'required_a': required, 'available_a': available,
            'required_kva': design_va * headroom / 1000,
            'required_kw': design_kw * headroom,
            'status': 'insufficient' if short else 'unknown' if unknown else 'covered'}
