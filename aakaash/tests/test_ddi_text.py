# SOURCE: NOT IN PAPERS. FIXTURES ONLY: hand-written sentences.
from medsafe.ddi_text import find_source_term, mark_sentence, strip_markers


def test_marks_both_drugs_earlier_first():
    p = mark_sentence("Warfarin levels rise with aspirin.", "aspirin", "warfarin")
    assert p.marked_text == "<e1>Warfarin</e1> levels rise with <e2>aspirin</e2>."
    assert strip_markers(p.marked_text) == p.text


def test_repeated_name_picks_nearest_pair_once():
    s = "Aspirin is common. Do not combine with aspirin and warfarin."
    p = mark_sentence(s, "aspirin", "warfarin")
    assert p.mentions1 == 2 and p.mentions2 == 1
    assert p.marked_text == "Aspirin is common. Do not combine with <e1>aspirin</e1> and <e2>warfarin</e2>."


def test_tie_goes_to_earliest():
    p = mark_sentence("warfarin aspirin warfarin", "aspirin", "warfarin")
    assert p.marked_text == "<e1>warfarin</e1> <e2>aspirin</e2> warfarin"


def test_case_and_whole_word_only():
    assert mark_sentence("ASPIRIN with WARFARIN", "aspirin", "warfarin") is not None
    assert mark_sentence("Aspirins with warfarin", "aspirin", "warfarin") is None  # not a whole word


def test_not_markable_cases():
    assert mark_sentence("Aspirin raises bleeding risk.", "aspirin", "warfarin") is None      # drug missing
    assert mark_sentence("Aspirin with aspirin.", "aspirin", "Aspirin") is None               # same drug
    assert mark_sentence("", "a", "b") is None
    assert mark_sentence("Aspirin and warfarin", "aspirin", "aspirin and warfarin") is None   # overlap only


def test_find_source_term():
    s = "Acetaminophen may raise the INR in patients taking warfarin."
    assert find_source_term(s, "Acetaminophen", ["warfarin", "coumadin"]) == "warfarin"
    assert find_source_term("Acetaminophen may raise the INR.", "Acetaminophen", ["warfarin"]) is None
    assert find_source_term("Warfarin and acetaminophen.", "acetaminophen", ["acetaminophen"]) is None  # overlaps matched term
