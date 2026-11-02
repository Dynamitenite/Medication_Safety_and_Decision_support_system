# SOURCE: NOT IN PAPERS. FIXTURES ONLY: every catalogue row and label below is hand-written to
# exercise code paths. None of it is real catalogue or DailyMed data and none of it may appear in the UI.
import json

from medsafe.catalogue import build

EMPTY_DI = '{"drug": [], "brand": [], "effect": []}'


def row(id_, name, c1, c2="", salt="", price="10", disc="FALSE", pack="strip of 10 tablets",
        maker="Maker A", di=""):
    return {"id": id_, "name": name, "price": price, "Is_discontinued": disc, "manufacturer_name": maker,
            "type": "allopathy", "pack_size_label": pack, "short_composition1": c1, "short_composition2": c2,
            "salt_composition": salt, "medicine_desc": "", "side_effects": "", "drug_interactions": di}


ROWS = [
    row("1", "Dolotest 650 Tablet", "Paracetamol (650mg)", price="30", pack="strip of 15 tablets"),
    row("2", "Calpara 650 Tablet", "Paracetamol (650mg)", price="20", maker="Maker B"),
    row("3", "Parafen 500 Tablet", "Paracetamol (500mg)", price="10"),
    row("4", "Oldpara 650 Tablet", "Paracetamol  (650mg) ", price="5", disc="TRUE"),
    row("5", "Metfo 500 Tablet", "Metformin (500mg)", price="15"),
    row("6", "Metfocomb Tablet", "Metformin (500mg) ", " Glimepiride (1mg)", price="40"),
    row("7", "Glimet Tablet", "Metformin (500mg) ", " Glimepiride (1mg)",
        salt="Metformin (500mg) + Glimepiride (1mg) + Voglibose (0.2mg)", price="60"),
    row("8", "Glimetwo Tablet", "Metformin (500mg) ", " Glimepiride (1mg)",
        salt="Metformin (500mg) + Glimepiride (1mg)", price="50", di=EMPTY_DI),
    row("9", "Amoxyna Tablet", "Amoxycillin (NA)"),
    row("10", "Vaxi Vaccine", "Hepatitis B Vaccine (rDNA) (NA)"),
    row("11", "Conflicto Syrup", "Levosalbutamol (1mg/5ml) ", " Ambroxol (30mg/5ml)",
        salt="Bromhexine (4mg) + Guaifenesin (50mg)"),
    row("12", "Saline Drip", "Sodium Chloride (0.9% w/v)"),
    row("13", "Citro Syrup", "Sodium Citrate (500mg)"),
    row("14", "Warfa 5 Tablet", "Warfarin (5mg)",
        di='{"drug": ["Paracetamol", "Aspirin"], "brand": [" Cutbrand, Cu", " Other"], '
           '"effect": ["MODERATE", "SERIOUS"]}'),
    row("15", "Asthalin Inhaler", "Salbutamol (100mcg)"),
    row("16", "Calchlor Injection", "Calcium Chloride (10% w/v)"),
    row("17", "Calacet Tablet", "Calcium Acetate (667mg)"),
    row("18", "Potchlor Syrup", "Potassium Chloride (500mg)"),
    row("19", "Potcit Syrup", "Potassium Citrate (1100mg)"),
    row("20", "Parasyp 650 Syrup", "Paracetamol (650mg)", price="25", pack="bottle of 60 ml Syrup"),
    row("21", "Paradrops 650", "Paracetamol (650mg)", price="22", pack="bottle of 15 ml Drop"),
    row("22", "Calpara 650 Dry Syrup", "Paracetamol (500mg)", price="12", pack="bottle of 30 ml Oral Suspension"),
    row("23", "Estrosplit Tablet", "Estradiol (1mg)", "Estradiol (1mg)",
        salt="Estradiol (1mg) + Estradiol (1mg)", price="18"),
    row("24", "Estro 1 Tablet", "Estradiol (1mg)", price="9"),
    row("25", "Estrosplit Two Tablet", "Estradiol (1mg)", "Estradiol (1mg)",
        salt="Estradiol (1mg) + Estradiol (1mg)", price="14"),
    row("26", "Paraunclear Tablet", "Paracetamol (300mg)", "Paracetamol (700mg)",
        salt="Paracetamol (300mg) + Paracetamol (700mg)", price="7"),
]

SECTIONS = ["indications", "drug_interactions", "adverse_reactions"]


TABLET = [{"form": "TABLET", "routes": ["ORAL"]}]
INJECTION = [{"form": "INJECTION, SOLUTION", "routes": ["INTRAVENOUS"]}]


def lab(sid, product, ings, moieties, sections=SECTIONS, eff="20200101", maker="US Maker", forms=TABLET):
    return {"dosage_forms": forms, "set_id": sid, "products": [product], "generic": [], "ingredients": ings, "moieties": moieties,
            "moieties_raw": [m.upper() for m in moieties], "manufacturer": maker, "title": product,
            "effective_time": eff, "sections": list(sections), "source": "x.zip!in.zip", "member": "a.xml"}


LABELS = [
    lab("L-apap-1", "Acetaminophen Tablets", ["ACETAMINOPHEN"], ["acetaminophen"], sections=SECTIONS[:2]),
    lab("L-apap-2", "Acetaminophen Caplets", ["ACETAMINOPHEN"], ["acetaminophen"]),
    lab("L-warf", "Warfarin Sodium Tablets", ["WARFARIN SODIUM"], ["warfarin"]),
    lab("L-metf", "Metformin Tablets", ["METFORMIN HYDROCHLORIDE"], ["metformin"]),
    lab("L-combo", "Metformin and Glipizide", ["METFORMIN HYDROCHLORIDE", "GLIPIZIDE"], ["metformin", "glipizide"]),
    lab("L-nacl", "Sodium Chloride Injection", ["SODIUM CHLORIDE"], ["sodium cation", "chloride ion"], forms=INJECTION),
    lab("L-cacl", "Calcium Chloride Injection", ["CALCIUM CHLORIDE"], ["calcium cation", "chloride ion"], forms=INJECTION),
    lab("L-kcl", "Potassium Chloride Tablets", ["POTASSIUM CHLORIDE"], ["potassium cation", "chloride ion"]),
    lab("L-albut", "Albuterol Inhaler", ["ALBUTEROL SULFATE"], ["albuterol"],
        forms=[{"form": "AEROSOL, METERED", "routes": ["RESPIRATORY (INHALATION)"]}]),
    lab("L-empty", "Blood Bag", ["SODIUM CITRATE"], ["sodium citrate"], sections=[], forms=[]),
    # most sections, but an injection: a tablet brand must not default to it
    lab("L-apap-inj", "Acetaminophen Injection", ["ACETAMINOPHEN"], ["acetaminophen"],
        sections=SECTIONS + ["boxed_warning"], forms=INJECTION),
]

# parsed label text for the checker (what medicines.load_label would return)
PARSED = {
    "L-warf": {"set_id": "L-warf", "sections": {"drug_interactions": [
        {"text": "Acetaminophen may raise the INR. Monitor closely. Unrelated sentence."}]}},
    "L-apap-2": {"set_id": "L-apap-2", "sections": {"drug_interactions": [{"text": "No drugs named here."}]}},
    "L-apap-1": {"set_id": "L-apap-1", "sections": {}},
    "L-apap-inj": {"set_id": "L-apap-inj", "sections": {}},
    "L-metf": {"set_id": "L-metf", "sections": {}},
    "L-albut": {"set_id": "L-albut", "sections": {}},
}


def write_artifacts(art_dir, rows=ROWS, labels=LABELS):
    art_dir.mkdir(parents=True, exist_ok=True)
    data, report = build(rows, labels)
    data["meta"] = {"source": "fixture", "report": report, "dailymed_parts_loaded": ["x.zip"]}
    (art_dir / "catalogue.json").write_text(json.dumps(data), encoding="utf-8")
    (art_dir / "names.json").write_text(json.dumps({"labels": labels}), encoding="utf-8")
    return data, report
