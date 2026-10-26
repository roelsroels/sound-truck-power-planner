"""Self-contained, bounded engineering PDF export. Estimates are not installation approvals."""
from .supply import venue_assessment
from .i18n import LANGUAGE, translate

import io
import math
import unicodedata
from datetime import datetime, timezone
from html import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Flowable,
)

INK = colors.HexColor("#16232d")
MINT = colors.HexColor("#0c977d")
PALE = colors.HexColor("#eaf7f3")
MUTED = colors.HexColor("#526473")
LINE = colors.HexColor("#dae3e7")
LIGHT = colors.HexColor("#f3f6f8")
PAGE_W, PAGE_H = A4
WIDTH = PAGE_W - 84

styles = {
    "label": ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=MINT, spaceAfter=8),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=25, leading=30, textColor=INK, spaceAfter=7),
    "subtitle": ParagraphStyle("subtitle", fontSize=10, leading=15, textColor=MUTED, spaceAfter=16),
    "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=12, leading=17, textColor=INK, spaceBefore=16, spaceAfter=8, keepWithNext=True),
    "normal": ParagraphStyle("normal", fontSize=8.7, leading=13, textColor=INK),
    "small": ParagraphStyle("small", fontSize=7.4, leading=11, textColor=MUTED),
    "cell": ParagraphStyle("cell", fontSize=8, leading=11, textColor=INK),
    "tablehead": ParagraphStyle("tablehead", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=colors.white),
    "metric": ParagraphStyle("metric", fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=INK, alignment=TA_CENTER),
    "metriclabel": ParagraphStyle("metriclabel", fontName="Helvetica-Bold", fontSize=7, leading=10, textColor=MUTED, alignment=TA_CENTER),
}

def plain(value, limit=180):
    text = str(value if value is not None else "")[:limit]
    for before, after in (("—", " - "), ("–", "-"), ("×", "x"),
                          ("‘", "'"), ("’", "'"), ("•", "-")):
        text = text.replace(before, after)
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c)).encode("ascii", "replace").decode("ascii")

def para(value, kind="cell", limit=180):
    return Paragraph(escape(plain(translate(value), limit)).replace("\n", "<br/>"), styles[kind])

def number(value, default=0.0, minimum=0.0, maximum=1e7):
    try:
        value = float(value)
        return value if math.isfinite(value) and minimum <= value <= maximum else default
    except (TypeError, ValueError):
        return default

def optional_number(value):
    return None if value is None or value == "" else number(value)

class PhaseBars(Flowable):
    def __init__(self, phases, max_phase_va):
        Flowable.__init__(self)
        self.phases = phases
        self.limit = max(1, max_phase_va)
        self.width = WIDTH
        self.height = 88

    def draw(self):
        c = self.canv
        for index, phase in enumerate(("L1", "L2", "L3")):
            y = 66 - index * 29
            value = self.phases[phase]
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(1, y + 8, phase)
            c.setFont("Helvetica", 8)
            c.drawRightString(WIDTH - 2, y + 8, f"{value/1000:.2f} kVA")
            c.setFillColor(LIGHT)
            c.roundRect(30, y-2, WIDTH-33, 8, 3, fill=1, stroke=0)
            c.setFillColor(MINT if value <= self.limit else colors.HexColor("#cf603b"))
            c.roundRect(30, y-2, max(1, (WIDTH-33)*min(1,value/self.limit)), 8, 3, fill=1, stroke=0)

def page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(INK)
    canvas.rect(0, PAGE_H-17*mm, PAGE_W, 17*mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(42, PAGE_H-12*mm, "SOUND TRUCK   /   POWER PLANNER")
    canvas.setFillColor(LINE)
    canvas.setStrokeColor(LINE)
    canvas.line(42, 33, PAGE_W-42, 33)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(42, 22, translate("PRELIMINARY PLANNING REPORT - NOT AN ELECTRICAL DESIGN CERTIFICATE"))
    canvas.drawRightString(PAGE_W-42, 22, translate(f"Page {doc.page}"))
    canvas.restoreState()

def section(label):
    return Paragraph(translate(label).upper(), styles["section"])

def table(headers, rows, widths=None):
    cells = [[para(x, "tablehead") for x in headers]]
    cells += [[para(x) for x in row] for row in rows]
    t = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,0),INK), ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,LIGHT]),
        ("VALIGN",(0,0),(-1,-1),"TOP"), ("LEFTPADDING",(0,0),(-1,-1),9),
        ("RIGHTPADDING",(0,0),(-1,-1),9), ("TOPPADDING",(0,0),(-1,-1),7),
        ("BOTTOMPADDING",(0,0),(-1,-1),7), ("LINEBELOW",(0,-1),(-1,-1),.5,LINE),
    ]))
    return t

def metrics(cards):
    row = []
    for value,label in cards:
        row.append([para(value,"metric",70), para(label,"metriclabel",85)])
    t=Table([row],colWidths=[WIDTH/len(row)]*len(row))
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),PALE),("BOX",(0,0),(-1,-1),.5,LINE),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),16),("BOTTOMPADDING",(0,0),(-1,-1),14),
    ]))
    return t

def _build_pdf(project, equipment):
    if not isinstance(project,dict) or not isinstance(equipment,list) or len(equipment)>250:
        raise ValueError("Invalid report project")
    units=project.get("units",[])
    if not isinstance(units,list) or len(units)>200:
        raise ValueError("Maximum 200 units per report")
    by_id={e["id"]:e for e in equipment}
    phases={"L1":0.0,"L2":0.0,"L3":0.0}
    rows=[]; issues=[]; ref_va=design_va=ref_kw=design_kw=weight=footprint=0.
    unknown_weights=unknown_footprints=0
    for unit in units:
        if not isinstance(unit,dict):
            raise ValueError("Invalid cabinet")
        ident=unit.get("equipment_id")
        profile=by_id.get(ident)
        if profile is None:
            issues.append(f"Missing equipment profile: {plain(ident)}")
            continue
        phase=unit.get("phase")
        if phase not in phases:
            raise ValueError("Invalid phase")
        reference=number(profile.get("reference_va"))
        demand=number(profile.get("design_va"))
        pf=number(profile.get("power_factor"),.95,.01,1)
        phases[phase]+=demand
        ref_va+=reference
        design_va+=demand
        ref_kw+=reference*pf/1000
        design_kw+=demand*pf/1000
        wt=optional_number(profile.get("weight_kg"))
        if wt is None: unknown_weights+=1
        else: weight+=wt
        w=optional_number(profile.get("width_m"))
        d=optional_number(profile.get("depth_m"))
        if w is None or d is None: unknown_footprints+=1
        else: footprint+=w*d
        if demand<reference: issues.append(f"{plain(profile.get('name'))}: high-load below reference")
        if profile.get("confidence")!="verified": issues.append(f"{plain(profile.get('name'))}: unverified input estimates")
        rows.append((plain(profile.get("name"),50),phase,f"{reference/1000:.2f}",f"{demand/1000:.2f}",plain(profile.get("confidence","estimate"),15)))
    if not rows:
        raise ValueError("At least one valid cabinet is required")
    uses_generator=project.get("power_mode")!="battery"
    selected=number(project.get("generator_kva"),40,.01,10000)
    gen_pf=number(project.get("generator_pf"),.8,.1,1)
    headroom=1+number(project.get("headroom_pct"),25,0,300)/100
    phase_max=max(phases.values())
    required=max(design_va*headroom, design_kw*1000/gen_pf*headroom if uses_generator else 0,phase_max*3*1.1)
    required_kva=required/1000
    fixed=project.get("setup_mode")=="fixed"
    voltage=number(project.get("voltage_v"),230,1,1000)
    venue=venue_assessment(project,phases,design_va,design_kw,headroom,voltage)
    generator_classes=[10,15,20,25,30,40,50,60,80,100,125,150,200,250,300,400,500]
    suggested=next((k for k in generator_classes if k>=required_kva),math.ceil(required_kva/50)*50)
    duration=number(project.get("duration_h"),8,.1,100)
    multiplier=number(project.get("program_multiplier"),1,.1,5)
    usable=number(project.get("battery_use_fraction"),.8,.01,1)
    eff=number(project.get("inverter_efficiency"),.92,.01,1)
    average_kw=ref_kw*multiplier
    nominal_battery=average_kw*duration/(usable*eff)
    installed_battery=number(project.get("battery_installed_kwh"),0)
    inverter=number(project.get("inverter_kva"),0)
    runtime=(installed_battery*usable*eff/average_kw) if average_kw>0 else None
    v=project.get("vehicle") or {}
    if not isinstance(v, dict):
        raise ValueError("Invalid vehicle details")
    uses_battery=project.get("power_mode") in ("battery", "hybrid")
    gen_weight=optional_number(v.get("generator_weight_kg")) if uses_generator else None
    battery_weight=optional_number(v.get("battery_weight_kg")) if uses_battery else None
    other_weight=optional_number(v.get("other_weight_kg"))
    total_known=weight+sum(x for x in (gen_weight,battery_weight,other_weight) if x is not None)
    deck_l=optional_number(v.get("deck_length_m"))
    deck_w=optional_number(v.get("deck_width_m"))
    deck_area=deck_l*deck_w if deck_l and deck_w else None
    payload=optional_number(v.get("payload_kg"))
    buffer=io.BytesIO()
    doc=SimpleDocTemplate(buffer,pagesize=A4,rightMargin=42,leftMargin=42,
                          topMargin=28*mm,bottomMargin=18*mm,
                          title=f"Sound Truck - {plain(project.get('name','Project'),90)}",
                          author="Sound Truck Power Planner")
    parts=[]
    parts.append(Paragraph(translate("ENGINEERING / 01"),styles["label"]))
    parts.append(Paragraph(escape(plain(project.get("name","Mobile sound project"),110)),styles["title"]))
    timestamp=datetime.now(timezone.utc).strftime("%d %b %Y / %H:%M UTC")
    parts.append(Paragraph(translate(f"Power planning snapshot  |  {timestamp}  |  {len(rows)} connected loads"),styles["subtitle"]))
    parts.append(metrics([
        (f"{ref_kw:.1f} kW","REFERENCE DEMAND"),
        (f"{design_va/1000:.1f} kVA","HIGH-LOAD ENVELOPE"),
        (f"{required_kva:.1f} kVA","MIN. MODEL CAPACITY"),
    ]))
    parts.append(Spacer(1,9))
    parts.append(section("01 / Supply assessment"))
    parts.append(table(["Parameter","Calculated / selected"],[
        ("Setup", "Fixed / venue" if fixed else "Mobile / truck"),
        ("Fallback scenario" if fixed else "Power scenario",{"generator":"Generator-only","battery":"Battery-only","hybrid":"Hybrid screening"}.get(project.get("power_mode"),"Generator-only")),
        *([("Generator selected",f"{selected:.0f} kVA (prime rating must be verified)")] if uses_generator else []),
        ("Model requirement",f"{required_kva:.1f} kVA incl. {round((headroom-1)*100)}% nominal headroom and worst-phase proxy"),
        *([("Provisional rating check","ABOVE model threshold" if selected>=required_kva else "BELOW model threshold - revise source / balance")] if uses_generator else []),
        ("Typical programme estimate",f"{average_kw:.2f} kW at {multiplier:.2f}x programme multiplier"),
        *([("Standalone battery requirement",f"{nominal_battery:.1f} kWh nominal for {duration:g} hours"),
        ("Battery configured",f"{installed_battery:.1f} kWh nominal; estimated {runtime:.1f} h at reference load" if runtime is not None and installed_battery>0 else "No installed capacity specified"),
        ("Inverter configured",f"{inverter:.0f} kVA (per-phase and transient limits NOT assessed)" if inverter>0 else "Not specified")] if uses_battery else []),
        *([("Fuel allowance",f"{number(project.get('fuel_rate_lph'))*duration:.1f} L at entered {number(project.get('fuel_rate_lph')):.1f} L/h, before reserve" if project.get('fuel_rate_lph') is not None else "Not estimated - requires supplier fuel rate")] if uses_generator else []),
    ],[WIDTH*.44,WIDTH*.56]))
    parts.append(section("02 / Three-phase demand"))
    phase_note="Per-phase apparent high-load allowance. Bars compare against one third of selected generator rating; this does not certify alternator imbalance tolerance." if uses_generator else "High-load estimate by phase, against one third of the entered inverter capacity. Supplier must confirm per-phase limits."
    parts.append(Paragraph(translate(phase_note),styles["small"]))
    parts.append(Spacer(1,8))
    parts.append(PhaseBars(phases,(selected if uses_generator else inverter)*1000/3))
    parts.append(section("03 / Equipment schedule"))
    parts.append(table(["Cabinet / load","Phase","Ref kVA","High kVA","Data"], rows, [WIDTH*.43,WIDTH*.10,WIDTH*.14,WIDTH*.16,WIDTH*.17]))
    if fixed:
        parts.append(section("04 / Venue requirements and generator fallback"))
        parts.append(para(f"Request dedicated three-phase supply with neutral and protective earth at {voltage:g} V phase-to-neutral. Capacity below includes {round((headroom-1)*100)}% headroom and must remain available after other venue loads.","normal",450))
        venue_rows=[("Total apparent / real capacity",f"{venue['required_kva']:.2f} kVA / {venue['required_kw']:.2f} kW")]
        for phase in phases:
            available=venue['available_a'][phase]
            value="not confirmed" if available is None else f"{available:g} A"
            venue_rows.append((phase,f"Require {venue['required_a'][phase]:.1f} A; venue available {value}"))
        verdict={"covered":"Entered supply covers the numerical planning envelope; electrician confirmation required.",
                 "insufficient":"Venue supply is insufficient. Arrange a suitable fallback source or reduce/rebalance the load.",
                 "unknown":"Venue supply is not fully confirmed. Confirm with the venue or arrange a suitable fallback source."}[venue['status']]
        venue_rows.append(("Venue assessment",verdict))
        if uses_generator:
            venue_rows.append(("Generator fallback",f"{suggested:g} kVA minimum suggested class; selected {selected:g} kVA " + ("covers" if selected>=required_kva else "is below") + " the generator planning envelope."))
        if uses_battery:
            venue_rows.append(("Battery fallback",f"{nominal_battery:.1f} kWh nominal; inverter planning capacity at least {required_kva:.1f} kVA."))
        parts.append(table(["Venue supply","Planning requirement"],venue_rows,[WIDTH*.40,WIDTH*.60]))
        parts.append(para("Confirm connectors, distribution, protection and transient capability with the venue electrician. These are supply requirements, not breaker or cable selections. The fallback source needs separate approval; do not parallel with venue mains.","small",450))
    else:
        parts.append(section("04 / Vehicle planning"))
        parts.append(table(["Parameter","Planning value"],[
            ("Vehicle",plain(v.get("type","Not specified"),120)),
            ("Deck",f"{deck_l:g} x {deck_w:g} m = {deck_area:.2f} m2" if deck_area else "Dimensions not provided"),
            ("Known equipment / source weight",f"{total_known:.1f} kg (speaker: {weight:.1f} kg; source/accessories: {total_known-weight:.1f} kg)"),
            ("Payload",f"{payload:.1f} kg; preliminary remaining {payload-total_known:.1f} kg" if payload is not None else "Unknown"),
            ("Incomplete measurements",f"{unknown_weights} speaker weights; {unknown_footprints} cabinet footprints unknown"),
            ("Known cabinet footprint",f"{footprint:.2f} m2 (not a fit / stack check)"),
        ],[WIDTH*.40,WIDTH*.60]))
    parts.append(section("05 / Evidence and engineering limitations"))
    parts.append(Paragraph(translate("Published audio output power is not mains consumption. High-load design values may be estimates derived from different manufacturer test conditions. Verify real cabinet inlet ratings, inrush, generator transients, phase limits, earthing/bonding, RCD selection, conductor protection, fuel, noise and operation while moving before use."),styles["normal"]))
    parts.append(Spacer(1,8))
    for i,issue in enumerate(dict.fromkeys(issues)):
        if i>=18:
            parts.append(para("Additional unverified entries omitted.", "small"))
            break
        parts.append(para("- "+issue,"small",220))
    parts.append(Spacer(1,12))
    parts.append(section("06 / Source references"))
    seen=set()
    for unit in units:
        item=by_id.get(unit.get("equipment_id")) if isinstance(unit,dict) else None
        if not item or item["id"] in seen: continue
        seen.add(item["id"])
        source=plain(item.get("source_url") or "User-entered / no manufacturer URL",140)
        parts.append(para(f"{plain(item.get('name'))}: {source}", "small",270))
        parts.append(para("Reference: "+plain(item.get("reference_basis"),200)+"; Design: "+plain(item.get("design_basis"),220),"small",440))
        parts.append(Spacer(1,5))
    # Optional V2 field evidence is a historical measurement snapshot, not a transient test.
    measurement=project.get("meter_summary")
    parts.append(section("07 / Measured programme data"))
    if isinstance(measurement,dict) and measurement.get("kind")=="measured-ac-real-power":
        parts.append(table(["Measured parameter","Observation"], [
            ("Average real input",f"{number(measurement.get('average_kw')):.2f} kW"),
            ("Highest sampled real input",f"{number(measurement.get('observed_peak_kw')):.2f} kW (NOT an instantaneous surge measurement)"),
            ("Energy observed",f"{number(measurement.get('energy_kwh')):.2f} kWh"),
            ("Observation window",f"{number(measurement.get('minutes')):.1f} minutes, {int(number(measurement.get('samples')))} samples"),
            ("Largest sample gap",f"{number(measurement.get('largest_gap_min')):.1f} minutes"),
        ],[WIDTH*.45,WIDTH*.55]))
    else:
        parts.append(para("No imported three-phase meter summary; nominal reference consumption is used.","small"))

    if uses_generator:
        parts.append(section("08 / Supplier generator fuel curve"))
        fuel=project.get("generator_fuel_curve")
        if isinstance(fuel,dict):
            pts=[25,50,75,100]
            raw=[fuel.get("p"+str(p)) for p in pts]
            rate=[number(n,0) if n is not None else 0 for n in raw]
            parts.append(para("Generator model: "+plain(fuel.get("model","Unspecified"),130),"normal"))
            parts.append(para("Supplier/source: "+plain(fuel.get("source","Unspecified"),200),"small"))
            parts.append(table(["Load","Fuel L/h"], [(f"{p}%",f"{rate[i]:.2f}" if rate[i]>0 else "Missing") for i,p in enumerate(pts)],[WIDTH*.45,WIDTH*.55]))
            if all(v>0 for v in rate) and all(rate[i]>=rate[i-1] for i in range(1,4)):
                measured_avg=number(measurement.get("average_kw")) if isinstance(measurement,dict) and measurement.get("kind")=="measured-ac-real-power" else average_kw
                target=100*measured_avg/(selected*gen_pf)
                if 25<=target<=100:
                    j=1
                    while j<3 and target>pts[j]:j+=1
                    frac=(target-pts[j-1])/(pts[j]-pts[j-1])
                    lph=rate[j-1]+frac*(rate[j]-rate[j-1])
                    parts.append(para(f"At {target:.1f}% estimated prime load: {lph:.2f} L/h; {lph*duration:.1f} L over {duration:g} h before reserve. Linear interpolation, NOT a guarantee.","normal",380))
                else:
                    parts.append(para(f"Estimated load {target:.1f}% falls outside published 25-100% curve; no extrapolation is made.","small",250))
            else:
                parts.append(para("Fuel data are missing or inconsistent; estimate withheld.","small"))
        else:
            parts.append(para("No generator supplier fuel curve entered.","small"))

    parts.append(section("09 / Cable and protection handoff"))
    parts.append(para("Values below are user-entered planning notes, not computed cable or breaker requirements. Engineer review flag is not an electrical certificate.","small",400))
    circuit_notes=project.get("circuit_notes")
    if not isinstance(circuit_notes,dict): circuit_notes={}
    cable_rows=[]
    for i,unit in enumerate(units):
        if not isinstance(unit,dict):continue
        item=by_id.get(unit.get("equipment_id")) or {}
        note=circuit_notes.get(str(i)) or {}
        if not isinstance(note,dict):note={}
        length=note.get("length_m")
        breaker=note.get("breaker_a")
        area=note.get("cable_mm2")
        cable_rows.append((
            f"{i+1}. {plain(item.get('name','Unknown'),36)}",
            plain(unit.get("phase",""),5),
            f"{number(item.get('design_va'))/230:.1f}",
            f"{number(length):g}" if length is not None else "-",
            f"{number(breaker):g}" if breaker is not None else "-",
            f"{number(area):g}" if area is not None else "-",
            "Marked" if note.get("engineer_reviewed") is True else "Pending"
        ))
    parts.append(table(["Load","Phase","Est A*","m","Breaker A","mm2","Review"],cable_rows,
                       [WIDTH*.32,WIDTH*.09,WIDTH*.11,WIDTH*.09,WIDTH*.15,WIDTH*.10,WIDTH*.14]))
    parts.append(para("*Phase current is an indicative 230 V apparent-current equivalent, NOT conductor ampacity. Confirm actual voltage, protective devices, fault-loop and installation standards.","small",500))
    doc.build(parts,onFirstPage=page,onLaterPages=page)
    return buffer.getvalue()


def build_pdf(project, equipment):
    token = LANGUAGE.set('nl' if isinstance(project, dict) and project.get('language') == 'nl' else 'en')
    try:
        return _build_pdf(project, equipment)
    finally:
        LANGUAGE.reset(token)
