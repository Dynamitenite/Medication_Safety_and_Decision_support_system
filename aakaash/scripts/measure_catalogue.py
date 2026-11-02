# SOURCE: NOT IN PAPERS (own tooling). Measures the real artifacts/catalogue.json; nothing is estimated.
"""Load time, memory and suggest latency of the catalogue as the API loads it.

From the aakaash folder:  .venv\\Scripts\\python.exe scripts\\measure_catalogue.py
Memory: tracemalloc (Python allocations) and, on Windows, the process working set before and after.
"""
from __future__ import annotations

import ctypes
import json
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

AAKAASH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AAKAASH))

from medsafe.catalogue import Catalogue  # noqa: E402

QUERIES = ["do", "dol", "dolo", "dolo 6", "cr", "cro", "crocin", "me", "met", "metf", "metformin", "par",
           "para", "paracetamol", "paracetmol", "acetaminophen", "aug", "augmentin", "azi", "azithral",
           "pan", "pantop", "telma", "amlo", "amlodipine", "thyronorm", "thyroxine", "salbutamol", "asthalin",
           "zzqx", "clav", "glimep", "rosuv", "atorva", "ecosprin", "calpol", "combiflam", "allegra", "montair",
           "levocet", "cefix", "ofloxacin", "amoxyclav", "sinarest", "vicks", "becosules", "shelcal", "liv 52",
           "ondem", "zerodol"]


def working_set_mb() -> float | None:
    if sys.platform != "win32":
        return None

    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    c = PMC()
    c.cb = ctypes.sizeof(PMC)
    k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_ulong]
    if not psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
        return None
    return c.WorkingSetSize / 2**20


def main() -> None:
    path = AAKAASH / "artifacts" / "catalogue.json"
    ws0 = working_set_mb()
    t0 = time.perf_counter()
    cat = Catalogue(json.loads(path.read_text(encoding="utf-8")))
    load_s = time.perf_counter() - t0
    ws1 = working_set_mb()
    del cat
    tracemalloc.start()
    cat = Catalogue(json.loads(path.read_text(encoding="utf-8")))
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"file: {path.stat().st_size / 1e6:.2f} MB  load (json + index): {load_s:.2f} s")
    print(f"python allocations held after load: {cur / 2**20:.0f} MiB  (peak during load {peak / 2**20:.0f} MiB)")
    if ws0 is not None:
        print(f"process working set: {ws0:.0f} MiB before, {ws1:.0f} MiB after the first load")
    for q in QUERIES:  # warm-up
        cat.suggest(q)
    times = []
    for _ in range(5):
        for q in QUERIES:
            t = time.perf_counter()
            cat.suggest(q)
            times.append((time.perf_counter() - t) * 1000)
    times.sort()
    p = lambda x: times[min(len(times) - 1, int(round(x * (len(times) - 1))))]
    print(f"suggest over {len(QUERIES)} queries x 5 runs ({len(times)} calls), in-process, limit 8:")
    print(f"   p50 {p(0.5):.2f} ms   p95 {p(0.95):.2f} ms   max {times[-1]:.2f} ms   mean {statistics.mean(times):.2f} ms")
    slow = sorted(((max((t := time.perf_counter(), cat.suggest(q), time.perf_counter() - t)[2:]) * 1000, q)
                   for q in QUERIES), reverse=True)[:5]
    print("   slowest queries (one run):", [(q, round(ms, 1)) for ms, q in slow])


if __name__ == "__main__":
    main()
