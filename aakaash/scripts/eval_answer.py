# SOURCE: NOT IN PAPERS. Our own check of the grounded-answer step. It measures only things the code can check
# (citations that exist, numbers that appear in the source, how often the model says "not found"). It makes NO
# accuracy claim: whether an answer is medically right needs a pharmacist reading the printed answers.
"""Run from the aakaash folder:  .venv\Scripts\python.exe scripts\eval_answer.py [questions.jsonl]

Needs the label index, the catalogue and LLM_API_KEY in the environment (live calls use the free-tier quota; the
limiter spaces them out). Lines of data/eval/questions.jsonl, one JSON object each (a line with "EXAMPLE": true is
skipped unless --examples is given):
  {"type": "ask", "medicine_id": "<catalogue id>", "question": "...", "scope": "default|all", "note": "..."}
  {"type": "simplify", "medicine_id": "<catalogue id>", "ingredient_index": 0, "section_key": "indications"}
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.config import get_settings  # noqa: E402
from api.schemas import AskRequest, SimplifyRequest  # noqa: E402
from api.services import answer as svc  # noqa: E402
from medsafe import answer as A, llm  # noqa: E402

DEFAULT = Path(__file__).resolve().parents[2] / "data" / "eval" / "questions.jsonl"


def rate(n: int, d: int) -> str:
    return f"{n}/{d} = {100 * n / d:.1f}%" if d else "n/a (none run)"


def main(argv: list[str]) -> int:
    use_examples = "--examples" in argv
    paths = [a for a in argv if not a.startswith("--")]
    path = Path(paths[0]) if paths else DEFAULT
    if not path.is_file():
        print(f"No questions file at {path}. Create it (see this script's docstring).")
        return 1
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if use_examples or not r.get("EXAMPLE")]
    if not rows:
        print("Only EXAMPLE lines found. Write your own questions, or pass --examples to run the examples.")
        return 1
    st = llm.status()
    if not st["ready"]:
        print(f"LLM not ready: {st['reason']}\nFix: {st['fix']}\nNo live call was made.")
        return 2
    settings = get_settings()
    print(f"provider={st['provider']} model={st['model']} questions={len(rows)}\n")
    ask_runs = []   # (response, cited sentences kept, cited sentences dropped)
    simp_runs = []
    skipped = []
    for i, r in enumerate(rows, 1):
        try:
            if r.get("type") == "ask":
                res = svc.ask(settings, AskRequest(medicine_id=r["medicine_id"], question=r["question"], scope=r.get("scope", "default")))
                if res.status == "ready":
                    kept = sum(1 for s in A._sentences(res.answer or "") if A.ids_in(s))
                    ask_runs.append((res, kept, res.dropped_sentences))
                else:
                    skipped.append((i, res.reason))
                print(f"[{i}] ASK {r['question']!r} (medicine {r['medicine_id']})")
                print("    ->", res.answer if res.status == "ready" else f"NOT READY: {res.reason}")
                if res.status == "ready":
                    print(f"    citations={res.citations} dropped={res.dropped_sentences} uncited={res.uncited_sentences} not_found={res.not_found}")
            elif r.get("type") == "simplify":
                res = svc.simplify(settings, SimplifyRequest(medicine_id=r["medicine_id"], ingredient_index=r.get("ingredient_index", 0),
                                                             section_key=r["section_key"]))
                if res.status == "ready":
                    simp_runs.append(res)
                else:
                    skipped.append((i, res.reason))
                print(f"[{i}] SIMPLIFY medicine {r['medicine_id']} / {r['section_key']}")
                if res.status == "ready":
                    print("    ORIGINAL:", (res.original or "")[:600].replace("\n", " "))
                    print("    REWRITE :", res.simplified)
                    print(f"    flagged={res.flagged} unmatched={res.unmatched}")
                else:
                    print("    NOT READY:", res.reason)
            else:
                skipped.append((i, f"unknown type {r.get('type')!r}"))
        except Exception as e:  # noqa: BLE001
            skipped.append((i, type(e).__name__ + ": " + llm.redact(str(e))[:200]))
        print()
        time.sleep(0.2)
    answered = [x for x in ask_runs if not x[0].not_found]
    kept = sum(x[1] for x in answered)
    dropped = sum(x[2] for x in ask_runs)
    print("=" * 70)
    print("Mechanical checks only. No accuracy claim: read the answers above and judge them yourself.")
    print(f"ask runs with a model reply     : {len(ask_runs)}")
    print(f"'Not found' rate                : {rate(sum(1 for x in ask_runs if x[0].not_found), len(ask_runs))}")
    print(f"citation validity (sentences whose cited ids all exist, before removal): {rate(kept, kept + dropped)}")
    print(f"simplify numbers+units consistent: {rate(sum(1 for s in simp_runs if not s.flagged), len(simp_runs))}")
    if skipped:
        print(f"not run / not ready ({len(skipped)}): " + "; ".join(f"#{i} {why}" for i, why in skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
