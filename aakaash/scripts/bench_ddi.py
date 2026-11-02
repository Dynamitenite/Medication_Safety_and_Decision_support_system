# SOURCE: NOT IN PAPERS (own tooling). Measures the CPU latency of the app's classifier path on this machine.
"""Latency of the interaction-type model on CPU, through the same service the API uses.

  .venv\\Scripts\\python.exe scripts\\bench_ddi.py [--model-dir artifacts/models/ddi_focal] [--n 10]
Prints: cold import + first-load time, then per-request time for classify (no explanation) and for
classify with Integrated Gradients (the "Why?" view). Run it again after placing the real checkpoint."""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

AAKAASH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AAKAASH))

SENTENCES = [
    ("Co-administration of probenecid with acyclovir increases the half-life of acyclovir.", "probenecid", "acyclovir"),
    ("Warfarin may be potentiated by aspirin, so avoid using them together.", "warfarin", "aspirin"),
    ("Clarithromycin raises simvastatin exposure and the risk of myopathy.", "clarithromycin", "simvastatin"),
    ("Sildenafil enhances the hypotensive effect of isosorbide mononitrate.", "sildenafil", "isosorbide mononitrate"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", type=Path, default=None)
    ap.add_argument("--n", type=int, default=8)
    a = ap.parse_args()
    t0 = time.perf_counter()
    from api.config import get_settings
    from api.schemas import DDIClassifyRequest
    from api.services import ddi

    s = get_settings()
    if a.model_dir:
        s = type(s)(**{**s.__dict__, "ddi_model_dir_override": a.model_dir.resolve()})
    if not ddi.model_state(s)["ready"]:
        sys.exit(ddi.model_state(s)["reason"])
    first = ddi.classify(s, DDIClassifyRequest(sentence=SENTENCES[0][0], drug_1=SENTENCES[0][1], drug_2=SENTENCES[0][2]))
    print(f"first request incl. imports and model load: {time.perf_counter() - t0:.1f} s (load {first.timing_ms['load']:.0f} ms)")
    for explain in (False, True):
        times = []
        for i in range(a.n):
            sent, d1, d2 = SENTENCES[i % len(SENTENCES)]
            sent = sent + " " * (i // len(SENTENCES))  # a distinct string, so the cache is not hit
            sent = sent.rstrip() + (" " * (i // len(SENTENCES)) + "." if i >= len(SENTENCES) else "")
            t = time.perf_counter()
            ddi.classify(s, DDIClassifyRequest(sentence=sent, drug_1=d1, drug_2=d2, explain=explain))
            times.append((time.perf_counter() - t) * 1000)
        print(f"{'with explanation (Integrated Gradients)' if explain else 'classify only'}: "
              f"median {statistics.median(times):.0f} ms, max {max(times):.0f} ms over {len(times)} requests")


if __name__ == "__main__":
    main()
