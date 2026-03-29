"""Simple benchmark example using BenchKit."""

from __future__ import annotations

import benchkit as bk


@bk.func("sort-comparison")
def sort_comparison(algorithm: str, size: int) -> None:
    """Benchmark a sorting algorithm on a random array."""
    result = bk.run(
        [
            "python3",
            "-c",
            (
                "import random, time, json; "
                f"data = [random.random() for _ in range({size})];"
                "t0 = time.perf_counter();"
                "sorted(data);"
                "elapsed = (time.perf_counter() - t0) * 1000;"
                "print(json.dumps({'elapsed_ms': elapsed, 'n_elements': len(data)}))"
            ),
        ],
        name="sort",
    )
    import json

    payload = json.loads(result.stdout)
    bk.context().save_result({
        "elapsed_ms": float(payload["elapsed_ms"]),
        "n_elements": int(payload["n_elements"]),
    })


CASES = bk.grid(algorithm=["timsort", "mergesort"], size=[1000, 10000, 100000])


def main() -> None:
    """Run the example benchmark sweep and print the results."""
    sort_comparison.sweep(cases=CASES, show_progress=False)
    frame = bk.load_frame("sort-comparison")
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
