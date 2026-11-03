# SOURCE: NOT IN PAPERS. FIXTURES ONLY: every medicine, allergy and name is hand-written test data.
# Tries every endpoint that reads or changes a user's own rows with another user's session. A row that
# belongs to someone else must look exactly like a row that does not exist (404, same body), and
# what is worked out from a user's data (risk analysis, profile summary) must never use another user's.
import pytest

from api.app import app

from test_intake import add_record, analyze, env, sign_in  # noqa: F401  (env is a fixture)

# collection -> (body that creates a row, body that would overwrite it)
COLLECTIONS = {
    "/api/allergies": ({"allergen": "Pollenx", "severity": "mild"}, {"allergen": "Hijack", "severity": "severe"}),
    "/api/conditions": ({"name": "Illone", "kind": "illness", "status": "current"}, {"name": "Hijack", "kind": "illness", "status": "current"}),
    "/api/medicine-records": ({"display_name": "Typedrug"}, {"display_name": "Hijack"}),
}


def _paths():
    return app.openapi()["paths"]


def _id_routes():
    """Every /api route that takes the id of one of the signed-in user's rows."""
    return sorted((method.upper(), path) for path, ops in _paths().items() if "{item_id}" in path for method in ops)


def test_every_route_that_takes_a_row_id_is_covered_below():
    covered = {(m, f"{url}/{{item_id}}") for url in COLLECTIONS for m in ("PUT", "DELETE")}
    assert set(_id_routes()) == covered, "a new route takes a row id: add it to COLLECTIONS"


def test_no_route_takes_a_user_id():
    for path in _paths():
        assert "user_id" not in path and "{user" not in path, path


@pytest.mark.parametrize("url", list(COLLECTIONS))
def test_other_users_session_gets_404_for_every_row_route(env, url):
    a, b = sign_in("a@example.com"), sign_in("b@example.com")
    create, hijack = COLLECTIONS[url]
    row = a.post(url, json=create).json()
    item = f"{url}/{row['id']}"
    missing = f"{url}/999999"
    for method, body in (("put", hijack), ("delete", None)):
        other = getattr(b, method)(item, **({"json": body} if body else {}))
        absent = getattr(b, method)(missing, **({"json": body} if body else {}))
        assert other.status_code == 404, (method, item)
        assert other.json() == absent.json(), "a row of someone else must look like a missing row"
        # the owner's request still works on the same row afterwards
    assert row["id"] in [r["id"] for r in a.get(url).json()]
    assert row["id"] not in [r["id"] for r in b.get(url).json()]
    assert a.put(item, json=create).status_code == 200
    assert a.delete(item).status_code == 204


def test_derived_results_never_use_another_users_data(env):
    a, b = sign_in("a@example.com"), sign_in("b@example.com")
    a.post("/api/allergies", json={"allergen": "Amoxicillin", "severity": "severe"})
    add_record(a, display_name="Warfarin tablet", catalogue_id="5")
    assert analyze(a, "9")["allergy_findings"], "the owner's own allergy is used"
    # B has no allergy and no current medicine: nothing of A's shows in B's analysis or summary
    other = analyze(b, "9")
    assert other["allergy_findings"] == [] and other["overall"] is None
    assert b.get("/api/profile/overview").json()["allergies"] == 0
    assert b.get("/api/profile/overview").json()["current_medicines"] == 0
    # a body that names someone else's rows is refused or ignored, never obeyed
    r = b.post("/api/analyze", json={"medicines": [{"catalogue_id": "9"}], "user_id": 1, "allergies": ["Amoxicillin"]})
    assert r.status_code in (200, 422)
    if r.status_code == 200:
        assert r.json()["allergy_findings"] == []


def test_deleting_one_account_leaves_the_other_users_rows(env):
    a, b = sign_in("a@example.com"), sign_in("b@example.com")
    for url, (create, _) in COLLECTIONS.items():
        a.post(url, json=create)
    assert b.delete("/api/account").status_code == 204
    assert [x["allergen"] for x in a.get("/api/allergies").json()].count("Pollenx") == 1
    assert "Illone" in [x["name"] for x in a.get("/api/conditions").json()]
    assert "Typedrug" in [x["display_name"] for x in a.get("/api/medicine-records").json()]
