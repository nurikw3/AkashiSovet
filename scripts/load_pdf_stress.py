from __future__ import annotations

import argparse
import asyncio
import math
from pathlib import Path
import sys
import time
from dataclasses import dataclass
from statistics import mean

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from stdlib.pdf import get_app_pdf_buffer, invalidate_pdf_cache
from stdlib.resources import init_resources, shutdown_resources


@dataclass
class RunResult:
    index: int
    app_id: int
    ok: bool
    elapsed_s: float
    error: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stress test for get_app_pdf_buffer() with percentile report."
    )
    parser.add_argument(
        "--app-id",
        type=int,
        action="append",
        dest="app_ids",
        required=True,
        help="Application ID to use. Repeat the flag to mix multiple app_ids.",
    )
    parser.add_argument(
        "-n",
        "--requests",
        type=int,
        default=50,
        help="Total number of requests to run. Default: 50.",
    )
    parser.add_argument(
        "-c",
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent workers. Default: 10.",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=3,
        help="Warmup requests before measuring. Default: 3.",
    )
    parser.add_argument(
        "--cold-cache",
        action="store_true",
        help="Invalidate PDF cache before each measured request.",
    )
    parser.add_argument(
        "--verbose-errors",
        action="store_true",
        help="Print all individual errors instead of only the summary.",
    )
    return parser.parse_args()


def percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    rank = math.ceil((p / 100.0) * len(sorted_values))
    idx = min(max(rank - 1, 0), len(sorted_values) - 1)
    return sorted_values[idx]


def format_ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f} ms"


async def single_run(index: int, app_id: int, cold_cache: bool) -> RunResult:
    t0 = time.perf_counter()
    try:
        if cold_cache:
            await invalidate_pdf_cache(app_id)
        await get_app_pdf_buffer(app_id)
        return RunResult(index=index, app_id=app_id, ok=True, elapsed_s=time.perf_counter() - t0)
    except Exception as exc:
        return RunResult(
            index=index,
            app_id=app_id,
            ok=False,
            elapsed_s=time.perf_counter() - t0,
            error=f"{type(exc).__name__}: {exc}",
        )


async def worker(
    worker_id: int,
    queue: asyncio.Queue[tuple[int, int]],
    results: list[RunResult],
    cold_cache: bool,
) -> None:
    while True:
        try:
            index, app_id = queue.get_nowait()
        except asyncio.QueueEmpty:
            return

        result = await single_run(index=index, app_id=app_id, cold_cache=cold_cache)
        results.append(result)

        status = "ok" if result.ok else "err"
        print(
            f"[worker {worker_id:02d}] req={result.index:04d} app_id={result.app_id} "
            f"status={status} elapsed={format_ms(result.elapsed_s)}"
        )
        queue.task_done()


def build_app_sequence(app_ids: list[int], requests: int) -> list[int]:
    return [app_ids[i % len(app_ids)] for i in range(requests)]


def print_report(results: list[RunResult], wall_s: float, verbose_errors: bool) -> None:
    successes = [r.elapsed_s for r in results if r.ok]
    errors = [r for r in results if not r.ok]
    successes_sorted = sorted(successes)

    total = len(results)
    ok_count = len(successes)
    err_count = len(errors)
    throughput = ok_count / wall_s if wall_s > 0 else 0.0

    print("\n=== Stress Test Report ===")
    print(f"total_requests: {total}")
    print(f"successes:      {ok_count}")
    print(f"errors:         {err_count}")
    print(f"wall_time:      {wall_s:.3f} s")
    print(f"throughput:     {throughput:.2f} req/s")

    if successes_sorted:
        print(f"avg:            {format_ms(mean(successes_sorted))}")
        print(f"min:            {format_ms(successes_sorted[0])}")
        print(f"p50:            {format_ms(percentile(successes_sorted, 50))}")
        print(f"p90:            {format_ms(percentile(successes_sorted, 90))}")
        print(f"p95:            {format_ms(percentile(successes_sorted, 95))}")
        print(f"p99:            {format_ms(percentile(successes_sorted, 99))}")
        print(f"max:            {format_ms(successes_sorted[-1])}")

    if errors:
        print("\nerror_summary:")
        counts: dict[str, int] = {}
        for item in errors:
            key = item.error or "Unknown error"
            counts[key] = counts.get(key, 0) + 1
        for message, count in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {count}x {message}")

        if verbose_errors:
            print("\nerror_details:")
            for item in errors:
                print(
                    f"  req={item.index:04d} app_id={item.app_id} "
                    f"elapsed={format_ms(item.elapsed_s)} error={item.error}"
                )


async def run(args: argparse.Namespace) -> int:
    if args.requests <= 0:
        print("--requests must be > 0", file=sys.stderr)
        return 2
    if args.concurrency <= 0:
        print("--concurrency must be > 0", file=sys.stderr)
        return 2
    if args.warmup < 0:
        print("--warmup must be >= 0", file=sys.stderr)
        return 2

    await init_resources()
    try:
        warmup_ids = build_app_sequence(args.app_ids, args.warmup)
        for idx, app_id in enumerate(warmup_ids, start=1):
            await single_run(index=idx, app_id=app_id, cold_cache=args.cold_cache)
        if args.warmup:
            print(f"Warmup complete: {args.warmup} request(s)")

        queue: asyncio.Queue[tuple[int, int]] = asyncio.Queue()
        for idx, app_id in enumerate(
            build_app_sequence(args.app_ids, args.requests), start=1
        ):
            queue.put_nowait((idx, app_id))

        results: list[RunResult] = []
        started_at = time.perf_counter()
        workers = [
            asyncio.create_task(worker(i + 1, queue, results, args.cold_cache))
            for i in range(args.concurrency)
        ]
        await asyncio.gather(*workers)
        wall_s = time.perf_counter() - started_at

        results.sort(key=lambda item: item.index)
        print_report(results, wall_s=wall_s, verbose_errors=args.verbose_errors)
        return 1 if any(not item.ok for item in results) else 0
    finally:
        await shutdown_resources()


def main() -> int:
    args = parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
