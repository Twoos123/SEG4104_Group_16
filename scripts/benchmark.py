"""Dynamic performance test: push requests through the full pipeline and time them.

Run:  python scripts/benchmark.py [number_of_requests]
"""

import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db, pipeline  # noqa: E402
from app.classifier import LocalClassifier  # noqa: E402
from etl.generate_history import generate  # noqa: E402


def main(n: int = 1000) -> dict:
    rows = [r for r in generate(n=n, seed=7) if r["description"]][:n]
    clf = LocalClassifier.load()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bench.db"
        db.init_db(path)
        times = []
        started = time.perf_counter()
        with db.session(path) as conn:
            for row in rows:
                t0 = time.perf_counter()
                pipeline.process_request(conn, clf, row["description"], row["location"], "WEB")
                times.append((time.perf_counter() - t0) * 1000)
            metrics = pipeline.metrics(conn)
        total = time.perf_counter() - started
    times.sort()
    result = {
        "requests": len(rows),
        "total_seconds": round(total, 2),
        "throughput_per_second": round(len(rows) / total, 1),
        "mean_ms": round(statistics.mean(times), 2),
        "p95_ms": round(times[int(0.95 * len(times)) - 1], 2),
        "max_ms": round(times[-1], 2),
        "automation_rate": metrics["automation_rate"],
        "duplicates_merged": metrics["duplicates_merged"],
    }
    print(result)
    return result


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1000)
