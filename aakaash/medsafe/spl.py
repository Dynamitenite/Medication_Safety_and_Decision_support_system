# SOURCE: Checked on real files: dm_spl_release_human_rx_part6.zip (see aakaash/scripts/spl_check).
# Confirmed there: HL7 v3 namespace, the LOINC section codes below, the ingredient classes
# (ACTIB, ACTIM and ACTIR carry active ingredients; IACT, CNTM and INGR do not) and the XML paths
# used for active moiety, generic name and manufacturer. Anything else is UNVERIFIED.
# FROM PAPERS: P1 uses DailyMed SPL XML and the sections Adverse Reactions, Warnings and
# Precautions, Boxed Warnings, Drug Interactions. Indications, Contraindications, Precautions
# and Use in Specific Populations come from the task spec / the user (NOT IN PAPERS).
# The parser itself is NOT IN PAPERS.
"""DailyMed SPL parser that reads straight from (possibly nested) zips."""
from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from pathlib import Path

from lxml import etree

SECTION_CODES = {
    "34067-9": "indications",
    "34070-3": "contraindications",
    "34071-1": "warnings_precautions",  # legacy "Warnings"; merged with W&P (own choice)
    "43685-7": "warnings_precautions",
    "42232-9": "precautions",  # legacy "Precautions": its own section, not merged (user decision)
    "34066-1": "boxed_warning",
    "34084-4": "adverse_reactions",
    "34073-7": "drug_interactions",
    "43684-0": "specific_populations",
    "42228-7": "specific_populations",  # pregnancy
    "34081-0": "specific_populations",  # pediatric use
    "34082-8": "specific_populations",  # geriatric use
}
# Used only when the code is missing or unmapped, and only when the WHOLE title is the section
# name (optional trailing colon). A numbered title ("2.6 Dosage Modifications Due to Drug
# Interactions") or a longer one ("Drug Interaction Studies") never matches. On the first 200
# real labels the earlier unanchored regexes matched 21 sections, at least 12 of them wrong.
TITLE_FALLBACK = [
    (re.compile(r"boxed warning:?", re.I), "boxed_warning"),
    (re.compile(r"contraindications?:?", re.I), "contraindications"),
    (re.compile(r"adverse reactions?:?", re.I), "adverse_reactions"),
    (re.compile(r"(clinically significant )?drug([ /-]+drug)? interactions?:?", re.I),
     "drug_interactions"),
    (re.compile(r"warnings?( and precautions)?:?", re.I), "warnings_precautions"),
    (re.compile(r"precautions:?", re.I), "precautions"),
    (re.compile(r"indications?( (and|&) usage)?:?", re.I), "indications"),
    (re.compile(r"use in specific populations:?", re.I), "specific_populations"),
]
CANONICAL_SECTIONS = ("indications", "contraindications", "warnings_precautions",
                      "precautions", "boxed_warning", "adverse_reactions", "drug_interactions",
                      "specific_populations")
# Sections whose subsections that are captured on their own are cut out of their text, and the
# parser keeps looking inside them for those subsections. Every other matched section is taken
# whole (subsections folded in) and not searched further.
DESCEND_INTO = frozenset({"precautions"})
_NEWLINE_AFTER = {"paragraph", "item", "tr", "br", "list", "caption", "title"}
MAX_ZIP_DEPTH = 3
# ingredient/@classCode values that are active ingredients. On part6 the other classes are
# IACT (inactive), CNTM (excipients/packaging such as sodium hydroxide, latex) and INGR (kit parts:
# water, glycerin, parabens); those are not taken.
ACTIVE_CLASSES = ("ACTIB", "ACTIM", "ACTIR")


def _ln(el) -> str:
    tag = el.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _text_of(el, skip=frozenset()) -> str:
    """Text of an element subtree; newline after block tags, space after table cells.
    Elements in `skip` are left out (their tail text is kept)."""
    parts = []

    def walk(node):
        if node.text:
            parts.append(node.text)
        for child in node:
            if isinstance(child.tag, str) and child not in skip:
                walk(child)
            if child.tail:
                parts.append(child.tail)
        name = _ln(node)
        if name in _NEWLINE_AFTER:
            parts.append("\n")
        elif name in ("td", "th"):
            parts.append(" ")

    walk(el)
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", "".join(parts))).strip()


def _first_child(el, name):
    if el is None:
        return None
    for c in el:
        if _ln(c) == name:
            return c
    return None


def _descend(el, *names):
    """Follow a chain of direct child element names; None if any step is missing."""
    for name in names:
        el = _first_child(el, name)
        if el is None:
            return None
    return el


def _clean_text(el) -> str | None:
    return el.text.strip() if el is not None and el.text and el.text.strip() else None


def normalize_ingredient(name: str) -> str:
    """Basic normalisation only (lowercase, drop parentheticals, collapse spaces). Salts are
    not stripped here: alternatives are matched on `active_moieties`, which carry no salt."""
    name = re.sub(r"\(.*?\)", " ", name.lower())
    return re.sub(r"\s+", " ", name).strip()


def _section_code_title(sec) -> tuple[str | None, str]:
    code_el = _first_child(sec, "code")
    title_el = _first_child(sec, "title")
    return (code_el.get("code") if code_el is not None else None,
            _text_of(title_el) if title_el is not None else "")


def _classify(code: str | None, title: str) -> tuple[str | None, str | None]:
    canon = SECTION_CODES.get(code or "")
    if canon is not None:
        return canon, "loinc_code"
    t = re.sub(r"\s+", " ", title).strip()
    if t:
        for rx, name in TITLE_FALLBACK:
            if rx.fullmatch(t):
                return name, "title_fallback"
    return None, None


def _collect_sections(el, out, methods, notes):
    """DFS over <section>. See DESCEND_INTO for the one section that is searched further."""
    for child in el:
        if not isinstance(child.tag, str):
            continue
        if _ln(child) == "section":
            code, title = _section_code_title(child)
            canon, how = _classify(code, title)
            if canon is not None:
                if canon in DESCEND_INTO:
                    skip = {s for s in child.iter()
                            if s is not child and _ln(s) == "section"
                            and _classify(*_section_code_title(s))[0] is not None}
                    text = _text_of(child, skip)
                    if text and text != title:
                        out.setdefault(canon, []).append(
                            {"code": code, "title": title, "text": text, "method": how})
                        methods[how] += 1
                    else:
                        notes[canon + "_only_subsections"] += 1
                    _collect_sections(child, out, methods, notes)
                    continue
                out.setdefault(canon, []).append(
                    {"code": code, "title": title, "text": _text_of(child), "method": how})
                methods[how] += 1
                continue  # do not descend into a matched section
        _collect_sections(child, out, methods, notes)


def parse_label(data: bytes, source: str = "", member: str = "") -> dict:
    """Parse one SPL XML. Raises on malformed XML or missing structure."""
    root = etree.fromstring(data)
    set_id_el = _first_child(root, "setId")
    set_id = set_id_el.get("root") if set_id_el is not None else None
    title_el = _first_child(root, "title")
    ver_el = _first_child(root, "versionNumber")
    eff_el = _first_child(root, "effectiveTime")
    moieties, names, generics = [], [], []
    active = []  # (classCode, name, moiety or None), one per distinct substance
    seen_substances = set()
    dosage_forms, seen_forms = [], set()  # [{form, routes}] per distinct product form
    for el in root.iter():
        n = _ln(el)
        if n == "ingredient":
            cls = el.get("classCode", "")
            if cls not in ACTIVE_CLASSES:
                continue
            sub = _first_child(el, "ingredientSubstance")
            name = _clean_text(_first_child(sub, "name"))
            if name is None:
                continue
            code_el = _first_child(sub, "code")  # UNII; every active ingredient on part6 has one
            key = code_el.get("code") if code_el is not None and code_el.get("code")                 else normalize_ingredient(name)
            if key in seen_substances:  # same substance in several products/parts of one label
                continue
            seen_substances.add(key)
            # real path: ingredient/ingredientSubstance/activeMoiety/activeMoiety/name
            moiety = _clean_text(_descend(sub, "activeMoiety", "activeMoiety", "name"))
            active.append((cls, name, moiety))
        elif n == "activeMoiety":
            nm = _first_child(el, "name")
            if nm is not None and nm.text:
                moieties.append(nm.text.strip())
        elif n == "manufacturedProduct":
            nm = _first_child(el, "name")
            if nm is not None and nm.text:
                names.append(nm.text.strip())
            # real paths (part6): manufacturedProduct/manufacturedProduct/formCode and, on the outer
            # one, consumedIn/substanceAdministration/routeCode (both carry a displayName)
            form_el = _descend(el, "manufacturedProduct", "formCode")
            if form_el is not None and form_el.get("displayName"):
                routes = sorted({r.get("displayName") for r in el.iter()
                                 if _ln(r) == "routeCode" and r.get("displayName")})
                pair = (form_el.get("displayName"), tuple(routes))
                if pair not in seen_forms:
                    seen_forms.add(pair)
                    dosage_forms.append({"form": pair[0], "routes": list(pair[1])})
        elif n == "genericMedicine":  # real path: .../asEntityWithGeneric/genericMedicine/name
            g = _clean_text(_first_child(el, "name"))
            if g:
                generics.append(g)
    if active:
        ingredients = [a[1] for a in active]
        moiety_raw = [a[2] for a in active if a[2]]
        missing = sum(1 for a in active if a[2] is None)
        source_name = "+".join(c for c in ACTIVE_CLASSES if any(a[0] == c for a in active))
    else:  # no ACTIB/ACTIM/ACTIR with a name: fall back to any activeMoiety name
        ingredients, moiety_raw, missing = moieties, moieties, 0
        source_name = "activeMoiety" if moieties else "none"
    # real path: document/author/assignedEntity/representedOrganization/name (direct child only)
    manufacturer = _clean_text(_descend(root, "author", "assignedEntity",
                                        "representedOrganization", "name"))
    sections: dict = {}
    methods: Counter = Counter()
    notes: Counter = Counter()
    body = None
    for el in root.iter():
        if _ln(el) == "structuredBody":
            body = el
            break
    if body is not None:
        _collect_sections(body, sections, methods, notes)
    return {
        "set_id": set_id,
        "title": _text_of(title_el) if title_el is not None else "",
        "version": ver_el.get("value") if ver_el is not None else None,
        "effective_time": eff_el.get("value") if eff_el is not None else None,
        "product_names": sorted(set(names)),
        "generic_names": sorted({g.lower(): g for g in reversed(generics)}.values()),
        "manufacturer": manufacturer,
        "dosage_forms": dosage_forms,
        "ingredients": sorted({normalize_ingredient(i) for i in ingredients if i}),
        "ingredients_raw": sorted(set(ingredients)),
        "active_moieties": sorted({normalize_ingredient(i) for i in moiety_raw if i}),
        "active_moieties_raw": sorted(set(moiety_raw)),
        "ingredients_without_moiety": missing,
        "ingredient_source": source_name,
        "sections": sections,
        "section_methods": dict(methods),
        "parse_notes": dict(notes),
        "source": source, "member": member,
    }


def _walk_zip(zf: zipfile.ZipFile, source: str, depth: int, stats: Counter):
    for info in zf.infolist():
        if info.is_dir():
            continue
        name, low = info.filename, info.filename.lower()
        if low.endswith(".xml"):
            yield source, name, zf.read(info)
        elif low.endswith(".zip"):
            if depth >= MAX_ZIP_DEPTH:
                stats["nested_zip_too_deep"] += 1
                continue
            try:
                inner = zipfile.ZipFile(io.BytesIO(zf.read(info)))
            except zipfile.BadZipFile:
                stats["bad_nested_zip"] += 1
                continue
            yield from _walk_zip(inner, f"{source}!{name}", depth + 1, stats)
        else:
            stats["other_member_" + (Path(low).suffix or "noext")] += 1


def iter_part(zip_path: Path, stats: Counter, max_labels: int | None = None):
    """Yield parsed label dicts for one DailyMed zip. Failures are counted, never silent."""
    n = 0
    with zipfile.ZipFile(zip_path) as zf:
        for source, member, data in _walk_zip(zf, zip_path.name, 1, stats):
            try:
                rec = parse_label(data, source, member)
            except Exception as exc:  # noqa: BLE001 - counted and reported
                stats["parse_failures"] += 1
                stats["parse_failure_" + type(exc).__name__] += 1
                continue
            if not rec["set_id"]:
                stats["missing_set_id"] += 1
            if not rec["manufacturer"]:
                stats["missing_manufacturer"] += 1
            if not rec["generic_names"]:
                stats["missing_generic_name"] += 1
            if rec["ingredients_without_moiety"]:
                stats["labels_with_ingredient_without_moiety"] += 1
            for k, v in rec["parse_notes"].items():
                stats["note_" + k] += v
            stats["labels_parsed"] += 1
            yield rec
            n += 1
            if max_labels is not None and n >= max_labels:
                return


def iter_parts(data_dir: Path, stats_by_part: dict | None = None,
               max_labels_per_part: int | None = None):
    """Loop over whichever dm_spl_release_human_rx_part*.zip files exist (sorted)."""
    for zp in sorted(data_dir.glob("*.zip")):
        st = Counter()
        if stats_by_part is not None:
            stats_by_part[zp.name] = st
        yield from iter_part(zp, st, max_labels_per_part)
