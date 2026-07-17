#!/usr/bin/env python3
"""Import a captioned image set through the live API and measure retrieval."""

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
import time
from typing import Any

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark MuseLens through its real import and text-search HTTP APIs."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument(
        "--sample-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "evaluation" / "coco-val2017",
    )
    parser.add_argument("--checkpoints", type=int, nargs="+", default=[1000, 5000])
    parser.add_argument("--import-batch-size", type=int, default=500)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT
        / "artifacts"
        / "evaluations"
        / "coco-val2017-live-api-v1.json",
    )
    return parser.parse_args()


def read_manifest(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = min(round((len(ordered) - 1) * fraction), len(ordered) - 1)
    return ordered[position]


def wait_for_job(client: httpx.Client, base_url: str, job_id: str) -> dict[str, Any]:
    previous = (-1, "")
    while True:
        response = client.get(f"{base_url}/v1/import-jobs/{job_id}")
        response.raise_for_status()
        job = response.json()
        current = (job["processed_files"], job["status"])
        if current != previous:
            print(
                f"import_job id={job_id} status={job['status']} "
                f"processed={job['processed_files']}/{job['total_files']} "
                f"imported={job['imported_files']} duplicates={job['duplicate_files']} "
                f"failed={job['failed_files']}",
                flush=True,
            )
            previous = current
        if job["status"] in {"completed", "partial", "failed"}:
            return job
        time.sleep(1)


def import_records(
    client: httpx.Client,
    base_url: str,
    image_dir: Path,
    records: list[dict[str, Any]],
    batch_size: int,
) -> list[dict[str, Any]]:
    jobs = []
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        with ExitStack() as stack:
            files = [
                (
                    "files",
                    (
                        record["filename"],
                        stack.enter_context((image_dir / record["filename"]).open("rb")),
                        "image/jpeg",
                    ),
                )
                for record in batch
            ]
            started = time.perf_counter()
            response = client.post(f"{base_url}/v1/import-jobs", files=files)
            response.raise_for_status()
        job = wait_for_job(client, base_url, response.json()["job_id"])
        job["wall_seconds"] = time.perf_counter() - started
        jobs.append(job)
        if job["failed_files"]:
            raise RuntimeError(f"Import job {job['job_id']} had failed files: {job}")
    return jobs


def evaluate(
    client: httpx.Client,
    base_url: str,
    records: list[dict[str, Any]],
    top_k: int,
) -> dict[str, Any]:
    hits_at = {1: 0, 5: 0, 10: 0}
    empty = 0
    latencies = []
    result_counts = []
    failures = []

    for position, record in enumerate(records, start=1):
        query = record["captions"][0]
        started = time.perf_counter()
        response = client.post(
            f"{base_url}/v1/search/text",
            json={"query": query, "top_k": top_k},
        )
        response.raise_for_status()
        latency_ms = (time.perf_counter() - started) * 1000
        results = response.json()
        filenames = [item["filename"] for item in results]
        latencies.append(latency_ms)
        result_counts.append(len(results))
        empty += int(not results)
        try:
            rank = filenames.index(record["filename"]) + 1
        except ValueError:
            rank = None
        for cutoff in hits_at:
            hits_at[cutoff] += int(rank is not None and rank <= cutoff)
        if rank is None and len(failures) < 20:
            failures.append(
                {
                    "filename": record["filename"],
                    "query": query,
                    "returned": filenames,
                }
            )
        if position % 100 == 0 or position == len(records):
            print(
                f"evaluate queries={position}/{len(records)} "
                f"recall_at_1={hits_at[1] / position:.4f} "
                f"empty_rate={empty / position:.4f}",
                flush=True,
            )

    count = len(records)
    return {
        "queries": count,
        "recall_at_1": hits_at[1] / count,
        "recall_at_5": hits_at[5] / count,
        "recall_at_10": hits_at[10] / count,
        "empty_result_rate": empty / count,
        "mean_result_count": mean(result_counts),
        "mean_latency_ms": mean(latencies),
        "p95_latency_ms": percentile(latencies, 0.95),
        "p99_latency_ms": percentile(latencies, 0.99),
        "failure_examples": failures,
    }


def write_result(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    checkpoints = sorted(set(args.checkpoints))
    if not checkpoints or checkpoints[0] < 1:
        raise ValueError("Checkpoints must contain positive integers.")
    if args.import_batch_size < 1 or args.import_batch_size > 500:
        raise ValueError("--import-batch-size must be between 1 and 500.")
    if args.top_k < 10:
        raise ValueError("--top-k must be at least 10 to compute Recall@10.")

    records = read_manifest(args.sample_dir / "manifest.jsonl")
    if checkpoints[-1] > len(records):
        raise ValueError(f"Largest checkpoint exceeds the {len(records)} manifest records.")
    selected = records[: checkpoints[-1]]
    result: dict[str, Any] = {
        "experiment": "live-api-library-scale",
        "run_started_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "sample": str(args.sample_dir.resolve().relative_to(PROJECT_ROOT)),
        "checkpoints": [],
    }

    with httpx.Client(timeout=httpx.Timeout(600), trust_env=False) as client:
        health = client.get(f"{args.base_url}/health")
        health.raise_for_status()
        if health.json()["mode"] != "local":
            raise RuntimeError("The benchmark requires a writable local-mode server.")

        existing_response = client.get(f"{args.base_url}/v1/images")
        existing_response.raise_for_status()
        existing_names = {item["filename"] for item in existing_response.json()}
        print(f"server_ready existing_images={len(existing_names)}")

        for checkpoint in checkpoints:
            checkpoint_records = selected[:checkpoint]
            missing = [
                record for record in checkpoint_records if record["filename"] not in existing_names
            ]
            import_started = time.perf_counter()
            jobs = import_records(
                client,
                args.base_url,
                args.sample_dir / "images",
                missing,
                args.import_batch_size,
            )
            import_seconds = time.perf_counter() - import_started
            existing_names.update(record["filename"] for record in missing)

            indexed_response = client.get(f"{args.base_url}/v1/images")
            indexed_response.raise_for_status()
            indexed = indexed_response.json()
            indexed_filenames = {item["filename"] for item in indexed}
            evaluable = [
                record
                for record in checkpoint_records
                if record["filename"] in indexed_filenames
            ]
            print(
                f"checkpoint_imported target={checkpoint} indexed={len(indexed)} "
                f"new={len(missing)} seconds={import_seconds:.2f}",
                flush=True,
            )
            metrics = evaluate(client, args.base_url, evaluable, args.top_k)
            checkpoint_result = {
                "target_images": checkpoint,
                "indexed_images": len(indexed),
                "new_images": len(missing),
                "import_seconds": import_seconds,
                "import_throughput_images_per_second": (
                    len(missing) / import_seconds if import_seconds else 0.0
                ),
                "jobs": jobs,
                "retrieval": metrics,
            }
            result["checkpoints"].append(checkpoint_result)
            write_result(args.output, result)
            print(json.dumps(checkpoint_result, ensure_ascii=False, indent=2), flush=True)

        result["run_completed_at"] = datetime.now(timezone.utc).isoformat()
        write_result(args.output, result)
        print(f"saved={args.output}")


if __name__ == "__main__":
    main()
