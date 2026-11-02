# SOURCE: NOT IN PAPERS. FIXTURES ONLY: the XML below is hand-written. Its element NESTING is copied
# from snippets seen in real DailyMed labels (dm_spl_release_human_rx_part6.zip, first 200 labels),
# but every name and sentence is invented. It is not data and proves nothing about real files;
# the real-file check is scripts/spl_check/compare_versions.py.
import unittest

from medsafe import spl
from medsafe.chunking import chunk_label

NS = 'xmlns="urn:hl7-org:v3"'


def section(code, title, body="", children=""):
    return (f'<component><section><code code="{code}"/><title>{title}</title>'
            f'<text>{body}</text>{children}</section></component>')


FIXTURE = f"""<document {NS}><id root="d"/><setId root="SET-FIX-2"/><title>FixDrug tablets</title>
<author><time/><assignedEntity><representedOrganization><name>Fix Labs Inc.</name>
<assignedEntity><assignedOrganization><name>Fix Labs Limited</name></assignedOrganization></assignedEntity>
</representedOrganization></assignedEntity></author>
<component><structuredBody>
{section("42232-9", "PRECAUTIONS", "General precaution sentence.",
         section("34073-7", "Drug Interactions", "FixDrug raises fixamol levels.") +
         section("42228-7", "Pregnancy", "Pregnancy sentence.") +
         section("34072-9", "General Precautions", "Unmapped subsection sentence."))}
{section("42229-5", "Drug Interactions", "Unclassified but exactly titled.")}
{section("42229-5", "2.6 Dosage Modifications Due to Drug Interactions", "Numbered, must not match.")}
{section("42229-5", "Drug Interaction Studies", "Longer title, must not match.")}
{section("42229-5", "Severe Cutaneous Adverse Reactions", "Must not match.")}
{section("42232-9", "PRECAUTIONS", "", section("34081-0", "Pediatric Use", "Pediatric sentence."))}
</structuredBody></component>
<subject><manufacturedProduct><manufacturedProduct><name>FixBrand</name>
<asEntityWithGeneric><genericMedicine><name>fixamide hydrochloride</name></genericMedicine></asEntityWithGeneric>
<ingredient classCode="ACTIB"><ingredientSubstance><name>FIXAMIDE HYDROCHLORIDE</name>
<activeMoiety><activeMoiety><name>FIXAMIDE</name></activeMoiety></activeMoiety></ingredientSubstance></ingredient>
<ingredient classCode="IACT"><ingredientSubstance><name>INACTIVE STARCH</name></ingredientSubstance></ingredient>
</manufacturedProduct></manufacturedProduct></subject></document>""".encode()


class SPLFixes(unittest.TestCase):
    def setUp(self):
        self.rec = spl.parse_label(FIXTURE)

    def test_moiety_generic_manufacturer(self):
        r = self.rec
        self.assertEqual(r["ingredients"], ["fixamide hydrochloride"])      # raw, for display
        self.assertEqual(r["ingredients_raw"], ["FIXAMIDE HYDROCHLORIDE"])
        self.assertEqual(r["active_moieties"], ["fixamide"])                # for matching
        self.assertEqual(r["ingredients_without_moiety"], 0)
        self.assertEqual(r["generic_names"], ["fixamide hydrochloride"])
        self.assertEqual(r["manufacturer"], "Fix Labs Inc.")  # not the nested organization

    def test_missing_moiety_is_counted_not_guessed(self):
        xml = FIXTURE.replace(b"<activeMoiety><activeMoiety><name>FIXAMIDE</name></activeMoiety></activeMoiety>", b"")
        r = spl.parse_label(xml)
        self.assertEqual(r["active_moieties"], [])
        self.assertEqual(r["ingredients_without_moiety"], 1)

    def test_precautions_is_its_own_section_without_duplicates(self):
        secs = self.rec["sections"]
        self.assertIn("precautions", secs)
        self.assertNotIn("warnings_precautions", secs)  # precautions is not merged into W&P
        text = secs["precautions"][0]["text"]
        self.assertIn("General precaution sentence.", text)
        self.assertIn("Unmapped subsection sentence.", text)       # unmapped subsection stays
        self.assertNotIn("raises fixamol", text)                    # captured as drug_interactions
        self.assertNotIn("Pregnancy sentence", text)                # captured as specific_populations
        di = " ".join(p["text"] for p in secs["drug_interactions"])
        self.assertIn("raises fixamol", di)
        self.assertIn("Pregnancy sentence", secs["specific_populations"][0]["text"])
        self.assertIn("Pediatric sentence", " ".join(p["text"] for p in secs["specific_populations"]))

    def test_precautions_with_only_captured_subsections_is_not_recorded(self):
        self.assertEqual(len(self.rec["sections"]["precautions"]), 1)  # the empty one is skipped
        self.assertEqual(self.rec["parse_notes"], {"precautions_only_subsections": 1})

    def test_title_fallback_needs_the_whole_title(self):
        titles = [(p["title"], p["method"]) for ps in self.rec["sections"].values() for p in ps]
        self.assertIn(("Drug Interactions", "title_fallback"), titles)
        blob = " ".join(p["text"] for ps in self.rec["sections"].values() for p in ps)
        for must_not in ("Numbered, must not match", "Longer title, must not match",
                         "Must not match."):
            self.assertNotIn(must_not, blob)

    def test_chunks_carry_new_metadata(self):
        ch = next(c for c in chunk_label(self.rec) if c["section"] == "precautions")
        self.assertEqual(ch["active_moieties"], ["fixamide"])
        self.assertEqual(ch["manufacturer"], "Fix Labs Inc.")
        self.assertEqual(ch["generic_names"], ["fixamide hydrochloride"])
        self.assertEqual(ch["product_names"], ["FixBrand"])


def ing(cls, unii, name, moiety=None):
    m = (f"<activeMoiety><activeMoiety><name>{moiety}</name></activeMoiety></activeMoiety>"
         if moiety else "")
    return (f'<ingredient classCode="{cls}"><ingredientSubstance><code code="{unii}"/>'
            f"<name>{name}</name>{m}</ingredientSubstance></ingredient>")


class ActiveIngredientClasses(unittest.TestCase):
    def parse(self, *ingredients):
        xml = (f'<document {NS}><setId root="S"/><subject><manufacturedProduct><manufacturedProduct>'
               f'<name>P</name>{"".join(ingredients)}</manufacturedProduct></manufacturedProduct>'
               f'</subject></document>').encode()
        return spl.parse_label(xml)

    def test_actib_actim_actir_together_and_inactive_classes_excluded(self):
        r = self.parse(
            ing("ACTIB", "U1", "SELENIOUS ACID", "SELENIOUS ACID"),
            ing("ACTIM", "U2", "ZINC SULFATE", "ZINC CATION"),
            ing("ACTIR", "U3", "LIDOCAINE HYDROCHLORIDE", "LIDOCAINE"),
            ing("IACT", "U4", "STARCH"), ing("CNTM", "U5", "SODIUM HYDROXIDE"),
            ing("INGR", "U6", "WATER"))
        self.assertEqual(r["ingredients"], ["lidocaine hydrochloride", "selenious acid", "zinc sulfate"])
        self.assertEqual(r["active_moieties"], ["lidocaine", "selenious acid", "zinc cation"])
        self.assertEqual(r["ingredient_source"], "ACTIB+ACTIM+ACTIR")

    def test_deduplicated_by_substance_code_not_by_spelling(self):
        r = self.parse(ing("ACTIB", "U1", "PAROXETINE HYDROCHLORIDE", "PAROXETINE"),
                       ing("ACTIB", "U1", "PAROXETINE HYDROCHLORIDE HEMIHYDRATE", "PAROXETINE"),
                       ing("ACTIB", "U1", "PAROXETINE HYDROCHLORIDE", "PAROXETINE"))
        self.assertEqual(r["ingredients"], ["paroxetine hydrochloride"])
        self.assertEqual(r["active_moieties"], ["paroxetine"])

    def test_actir_only_label_uses_actir(self):
        r = self.parse(ing("ACTIR", "U3", "IPRATROPIUM BROMIDE", "IPRATROPIUM"))
        self.assertEqual((r["ingredients"], r["ingredient_source"]), (["ipratropium bromide"], "ACTIR"))


class DosageFormTest(unittest.TestCase):
    """formCode sits at manufacturedProduct/manufacturedProduct/formCode and routeCode under the outer
    product's consumedIn (the nesting seen in real part6 labels); container forms are not taken."""

    XML = (f'<document {NS}><setId root="SET-FORM"/><title>FormDrug</title><subject><manufacturedProduct>'
           '<manufacturedProduct><name>FormBrand</name><formCode code="C42931" displayName="TABLET, FILM COATED"/>'
           '<asContent><containerPackagedProduct><formCode code="C43173" displayName="BOTTLE, PLASTIC"/>'
           '</containerPackagedProduct></asContent></manufacturedProduct>'
           '<consumedIn><substanceAdministration><routeCode code="C38288" displayName="ORAL"/>'
           '</substanceAdministration></consumedIn></manufacturedProduct></subject></document>').encode()

    def test_form_and_route(self):
        rec = spl.parse_label(self.XML)
        self.assertEqual(rec["dosage_forms"], [{"form": "TABLET, FILM COATED", "routes": ["ORAL"]}])

    def test_no_form(self):
        rec = spl.parse_label(f'<document {NS}><setId root="S"/><title>t</title></document>'.encode())
        self.assertEqual(rec["dosage_forms"], [])


if __name__ == "__main__":
    unittest.main()
