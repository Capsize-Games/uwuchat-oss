#!/usr/bin/env python3
"""Load-testing tool for FastSearch API endpoints.

Two modes:

``fixed`` (default)
    Bounded-concurrency benchmark — N requests total, at most M
    in-flight at once.  Useful for finding the server's raw ceiling.

``multi-customer``
    Simulates N independent customers, each issuing requests at
    randomized Poisson-process intervals.  Useful for answering:
    "how many concurrent customers can this handle before the
    observed peak concurrency crosses the safe threshold?"

Usage (local dev, run inside Docker)::

    # Fixed-concurrency mode:
    docker compose exec server python \\
        extensions/fastsearch/scripts/load_test.py \\
        --url http://172.17.0.1:18000 \\
        --api-key test-key \\
        --concurrency 3 --total-requests 30

    # Multi-customer mode:
    docker compose exec server python \\
        extensions/fastsearch/scripts/load_test.py \\
        --url http://172.17.0.1:18000 \\
        --api-key test-key \\
        --mode multi-customer \\
        --customers 5 --mean-interval 15 --duration 120

Interpreting multi-customer results
-----------------------------------
Run at increasing customer counts until the reported
**peak concurrent in-flight** exceeds the safe threshold
(established at ~2 for the current hardware) or the error
rate rises.  The output is self-describing — every parameter
that produced the run is printed in the header.

DO NOT point this at production without deliberate intent —
production URLs are never hardcoded as defaults.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import statistics
import sys
import time
from typing import List, Tuple

import aiohttp

# Default local FastSearch URL.
_DEFAULT_URL = os.environ.get(
    "FASTSEARCH_LOAD_TEST_URL",
    "http://127.0.0.1:8001",
)

_ENDPOINTS = [
    "/api/search/",
    "/api/news/latest-summary/",
]

_SAMPLE_QUERIES = [
    "python programming",
    "machine learning",
    "climate change",
    "space exploration",
    "quantum computing",
    "renewable energy",
    "artificial intelligence",
    "genetic engineering",
    "blockchain technology",
    "nuclear fusion",
]

# Shared result type.
Result = Tuple[str, float, int | None, str | None]


# ==================================================================
# CLI
# ==================================================================


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for both modes."""
    parser = argparse.ArgumentParser(
        description="Load-test FastSearch API endpoints",
        epilog=(
            "WARNING: Defaults target 127.0.0.1:8001 (local dev). "
            "Pointing at a real instance requires --url and "
            "--api-key — this is opt-in by design."
        ),
    )
    parser.add_argument(
        "--url",
        default=_DEFAULT_URL,
        help=f"FastSearch base URL (default: {_DEFAULT_URL})",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("FASTSEARCH_API_KEY", "test-key"),
        help="API key for X-API-Key header",
    )
    parser.add_argument(
        "--mode",
        choices=["fixed", "multi-customer"],
        default="fixed",
        help="Load-test mode: fixed-concurrency or "
             "multi-customer simulation (default: fixed)",
    )
    # ── fixed-concurrency params ──────────────────────────
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="[fixed] Simultaneous in-flight requests (default: 3)",
    )
    parser.add_argument(
        "--total-requests",
        type=int,
        default=30,
        help="[fixed] Total requests to send (default: 30)",
    )
    # ── multi-customer params ─────────────────────────────
    parser.add_argument(
        "--customers",
        type=int,
        default=5,
        help="[multi-customer] Number of simulated customers "
             "(default: 5)",
    )
    parser.add_argument(
        "--mean-interval",
        type=float,
        default=15.0,
        help="[multi-customer] Mean seconds between one "
             "customer's requests (Poisson arrivals, default: 15)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=120.0,
        help="[multi-customer] Simulation duration in seconds "
             "(default: 120)",
    )
    parser.add_argument(
        "--search-probability",
        type=float,
        default=1.0,
        help="[multi-customer] Probability (0.0-1.0) that a "
             "customer's turn triggers a search.  Default 1.0 "
             "(every turn).  Set to ~0.15 for realistic chat "
             "cadence where only ~15%% of messages trigger "
             "searches.",
    )
    # ── shared ────────────────────────────────────────────
    parser.add_argument(
        "--endpoint",
        choices=["search", "news", "all"],
        default="all",
        help="Which endpoint to test (default: all)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout in seconds (default: 30)",
    )
    return parser.parse_args()


# ==================================================================
# HTTP helpers
# ==================================================================


async def _do_one_request(
    session: aiohttp.ClientSession,
    base_url: str,
    api_key: str,
    endpoint: str,
    query: str,
    timeout: float,
) -> Result:
    """Send one request; return (endpoint, latency, status, error)."""
    url = f"{base_url.rstrip('/')}{endpoint}"
    headers = {
        "Accept": "application/json",
        "X-API-Key": api_key,
    }
    params: dict = {"q": query, "limit": 5}
    if endpoint == "/api/search/":
        params["type"] = "pages"
        params["page"] = "1"

    t0 = time.monotonic()
    try:
        async with session.get(
            url,
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            await resp.read()
            elapsed = time.monotonic() - t0
            return (endpoint, elapsed, resp.status, None)
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - t0
        return (endpoint, elapsed, None, "timeout")
    except aiohttp.ClientError as exc:
        elapsed = time.monotonic() - t0
        return (endpoint, elapsed, None, str(exc))
    except Exception as exc:
        elapsed = time.monotonic() - t0
        return (endpoint, elapsed, None, str(exc))


# ==================================================================
# Fixed-concurrency runner
# ==================================================================


async def _run_fixed(
    base_url: str,
    api_key: str,
    concurrency: int,
    total_requests: int,
    endpoints: List[str],
    timeout: float,
) -> List[Result]:
    """Bounded-concurrency benchmark."""
    semaphore = asyncio.Semaphore(concurrency)
    results: List[Result] = []

    async def _bounded(idx: int) -> None:
        async with semaphore:
            ep = endpoints[idx % len(endpoints)]
            q = _SAMPLE_QUERIES[idx % len(_SAMPLE_QUERIES)]
            async with aiohttp.ClientSession() as session:
                results.append(
                    await _do_one_request(
                        session, base_url, api_key, ep, q, timeout,
                    )
                )

    await asyncio.gather(
        *[_bounded(i) for i in range(total_requests)]
    )
    return results


# ==================================================================
# Multi-customer runner
# ==================================================================


async def _run_multi_customer(
    base_url: str,
    api_key: str,
    customers: int,
    mean_interval: float,
    duration: float,
    endpoints: List[str],
    timeout: float,
    search_probability: float = 1.0,
) -> Tuple[List[Result], int]:
    """Simulate N independent customers with Poisson arrivals.

    Each customer "wakes up" at randomized intervals drawn from
    an exponential distribution with mean *mean_interval*.  On
    each wake-up, there is a *search_probability* chance of
    actually firing a search request; otherwise the turn is a
    no-op (plain conversation, no API call).

    All customers stop after *duration* seconds.

    Returns (results, peak_concurrent_in_flight).
    """
    results: List[Result] = []
    in_flight: int = 0
    peak: int = 0
    lock = asyncio.Lock()

    async def _customer(customer_id: int) -> None:
        nonlocal in_flight, peak
        t = 0.0
        req_idx = 0
        async with aiohttp.ClientSession() as session:
            while t < duration:
                # Poisson arrival: wait exponential(mean_interval).
                wait = random.expovariate(1.0 / mean_interval)
                await asyncio.sleep(wait)
                t += wait
                if t >= duration:
                    break

                ep = endpoints[(customer_id + req_idx) % len(endpoints)]
                q = _SAMPLE_QUERIES[
                    (customer_id * 7 + req_idx) % len(_SAMPLE_QUERIES)
                ]
                req_idx += 1

                # Only fire a search on a fraction of turns.
                if random.random() >= search_probability:
                    continue

                async with lock:
                    in_flight += 1
                    if in_flight > peak:
                        peak = in_flight

                result = await _do_one_request(
                    session, base_url, api_key, ep, q, timeout,
                )

                async with lock:
                    in_flight -= 1

                results.append(result)

    tasks = [
        asyncio.create_task(_customer(i)) for i in range(customers)
    ]
    await asyncio.wait(tasks, timeout=duration + 5.0)

    # Cancel any stragglers.
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    return results, peak


# ==================================================================
# Shared reporting
# ==================================================================


def _percentile(values: List[float], pct: float) -> float:
    """Compute the *pct*-th percentile of sorted *values*."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = (len(sorted_vals) - 1) * pct / 100.0
    lower = int(idx)
    upper = min(lower + 1, len(sorted_vals) - 1)
    frac = idx - lower
    return sorted_vals[lower] * (1 - frac) + sorted_vals[upper] * frac


def _report(
    results: List[Result],
    *,
    peak_concurrency: int | None = None,
) -> None:
    """Print latency and error-rate summary."""
    latencies = [r[1] for r in results]
    # Any non-2xx status is a failure: 4xx (auth, not found),
    # 5xx (server error), and None (connection dropped).
    # 3xx should not occur for these endpoints.
    errors = [r for r in results if r[2] is None or r[2] >= 400]
    transient = [r for r in errors if r[2] in (502, 503, 504)]

    print(f"\n{'='*60}")
    print("FastSearch Load Test Results")
    print(f"{'='*60}")
    print(f"Total requests:     {len(results)}")
    print(f"Successful:         {len(results) - len(errors)}")
    print(f"Errors:             {len(errors)}")
    print(f"Transient (502-504):{len(transient)}")
    print(f"Other failures:     {len(errors) - len(transient)}")

    if peak_concurrency is not None:
        print(f"{'-'*60}")
        print(f"Peak concurrent in-flight: {peak_concurrency}")

    print(f"{'-'*60}")

    if latencies:
        print(f"Latency p50:        {_percentile(latencies, 50):.3f}s")
        print(f"Latency p95:        {_percentile(latencies, 95):.3f}s")
        print(f"Latency p99:        {_percentile(latencies, 99):.3f}s")
        print(f"Latency min:        {min(latencies):.3f}s")
        print(f"Latency max:        {max(latencies):.3f}s")
        print(f"Latency mean:       {statistics.mean(latencies):.3f}s")
        if len(latencies) > 1:
            print(
                f"Latency stdev:      "
                f"{statistics.stdev(latencies):.3f}s"
            )

    if errors:
        print(f"{'-'*60}")
        print("Error breakdown:")
        status_counts: dict = {}
        for _, _, status, msg in errors:
            label = str(status) if status else (msg or "unknown")
            status_counts[label] = status_counts.get(label, 0) + 1
        for label, count in sorted(status_counts.items()):
            print(f"  {label}: {count}")

    # Per-endpoint breakdown
    by_endpoint: dict = {}
    for ep, lat, status, _ in results:
        by_endpoint.setdefault(ep, []).append((lat, status))

    print(f"{'-'*60}")
    print("Per-endpoint summary:")
    for ep, items in sorted(by_endpoint.items()):
        ep_lats = [it[0] for it in items]
        ep_errs = [
            it for it in items if it[1] is None or it[1] >= 400
        ]
        ep_name = ep.rstrip("/").rsplit("/", 1)[-1] or ep
        print(
            f"  /{ep_name}/: {len(items)} req, "
            f"p50={_percentile(ep_lats, 50):.3f}s, "
            f"errors={len(ep_errs)}"
        )

    print(f"{'='*60}\n")

    if len(transient) > len(results) * 0.2:
        print(
            "FAIL: Transient error rate > 20% — "
            "service may be overloaded."
        )
        sys.exit(1)

    if results and len(errors) == len(results):
        print(
            "FAIL: 100%% of requests (%d) failed. "
            "Check authentication, URL, and network — "
            "these are not real search results."
            % len(results)
        )
        sys.exit(1)


# ==================================================================
# URL safety
# ==================================================================


def _check_url_is_local(url: str) -> bool:
    """Heuristic: return True when *url* looks like a local target."""
    if not url:
        return False
    url_lower = url.lower()
    local_hosts = (
        "127.0.0.1", "localhost", "fastsearch",
        "0.0.0.0", "[::1]",
    )
    return any(h in url_lower for h in local_hosts)


# ==================================================================
# Main
# ==================================================================


def main() -> None:
    """Entry point."""
    args = _parse_args()
    base_url = args.url.rstrip("/")

    if not _check_url_is_local(base_url):
        print(
            "WARNING: Target does not appear to be a local instance.\n"
            f"  URL: {base_url}\n"
            "  This script is for local dev testing only.\n"
            "  Press Ctrl+C within 5 seconds to abort.\n",
            flush=True,
        )
        time.sleep(5)

    endpoints: List[str] = []
    if args.endpoint in ("search", "all"):
        endpoints.append("/api/search/")
    if args.endpoint in ("news", "all"):
        endpoints.append("/api/news/latest-summary/")

    if not endpoints:
        print("ERROR: no endpoints selected")
        sys.exit(1)

    t0 = time.monotonic()
    peak_concurrency: int | None = None

    if args.mode == "multi-customer":
        print(
            f"Target:        {base_url}\n"
            f"Endpoints:     {', '.join(endpoints)}\n"
            f"Mode:          multi-customer\n"
            f"Customers:     {args.customers}\n"
            f"Mean interval: {args.mean_interval:.1f}s (Poisson)\n"
            f"Search prob:   {args.search_probability:.0%}\n"
            f"Duration:      {args.duration:.0f}s\n"
            f"Timeout:       {args.timeout}s\n"
            f"{'-'*40}",
            flush=True,
        )
        results, peak_concurrency = asyncio.run(
            _run_multi_customer(
                base_url=base_url,
                api_key=args.api_key,
                customers=args.customers,
                mean_interval=args.mean_interval,
                duration=args.duration,
                endpoints=endpoints,
                timeout=args.timeout,
                search_probability=args.search_probability,
            )
        )
    else:
        print(
            f"Target:      {base_url}\n"
            f"Endpoints:   {', '.join(endpoints)}\n"
            f"Mode:        fixed-concurrency\n"
            f"Concurrency: {args.concurrency}\n"
            f"Requests:    {args.total_requests}\n"
            f"Timeout:     {args.timeout}s\n"
            f"{'-'*40}",
            flush=True,
        )
        results = asyncio.run(
            _run_fixed(
                base_url=base_url,
                api_key=args.api_key,
                concurrency=args.concurrency,
                total_requests=args.total_requests,
                endpoints=endpoints,
                timeout=args.timeout,
            )
        )

    wall_time = time.monotonic() - t0
    print(f"\nWall-clock duration: {wall_time:.1f}s")
    _report(results, peak_concurrency=peak_concurrency)


if __name__ == "__main__":
    main()
