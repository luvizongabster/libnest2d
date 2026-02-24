#!/usr/bin/env python3
"""
Benchmark runner para a API Libnest2D (nest-local).
Compara diferentes options (selection, try_triplets, etc.) em casos fixos
e grava utilization, bins_used e runtime_ms.

Uso:
  python run_benchmark.py --api-url http://localhost:8080 --cases cases --configs configs/max_quality.yaml --out results/run1.csv
  (Requer API + worker + engine rodando, ex.: docker compose up -d)
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_job(api_url: str, payload: dict, poll_interval: float = 2.0, poll_timeout: float = 300.0) -> dict:
    """POST /jobs, poll GET /jobs/:id?embed=result until SUCCEEDED or FAILED. Returns result or raises."""
    base = api_url.rstrip("/")
    req = urllib.request.Request(
        f"{base}/jobs",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    job_id = data["job_id"]

    deadline = time.monotonic() + poll_timeout
    while time.monotonic() < deadline:
        with urllib.request.urlopen(f"{base}/jobs/{job_id}?embed=result", timeout=30) as resp:
            status_data = json.loads(resp.read().decode())
        st = status_data.get("status")
        if st == "SUCCEEDED":
            return status_data.get("result") or status_data
        if st == "FAILED":
            raise RuntimeError(status_data.get("error", "Job failed"))
        time.sleep(poll_interval)

    raise TimeoutError(f"Job {job_id} did not finish within {poll_timeout}s")


def main():
    parser = argparse.ArgumentParser(description="Run Libnest2D benchmark (cases x configs)")
    parser.add_argument("--api-url", default="http://localhost:8080", help="API base URL")
    parser.add_argument("--cases", default="cases", help="Directory with case JSON files")
    parser.add_argument("--configs", default="configs/max_quality.yaml", help="YAML file with list of configs")
    parser.add_argument("--out", default="results/benchmark.csv", help="Output CSV path")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Poll interval (s)")
    parser.add_argument("--poll-timeout", type=float, default=300.0, help="Max wait per job (s)")
    args = parser.parse_args()

    try:
        import yaml
    except ImportError:
        print("pip install pyyaml", file=sys.stderr)
        sys.exit(1)

    cases_dir = Path(args.cases)
    if not cases_dir.is_dir():
        print(f"Cases directory not found: {cases_dir}", file=sys.stderr)
        sys.exit(1)

    configs_path = Path(args.configs)
    if not configs_path.is_file():
        print(f"Configs file not found: {configs_path}", file=sys.stderr)
        sys.exit(1)

    with open(configs_path, "r", encoding="utf-8") as f:
        configs_data = yaml.safe_load(f)
    configs = configs_data.get("configs", [])
    if not configs:
        print("No configs in YAML", file=sys.stderr)
        sys.exit(1)

    case_files = sorted(cases_dir.glob("*.json"))
    if not case_files:
        print(f"No JSON cases in {cases_dir}", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for case_path in case_files:
        case_id = case_path.stem
        payload_base = load_json(case_path)
        for cfg in configs:
            name = cfg.get("name", "unnamed")
            options = cfg.get("options", {})
            payload = {**payload_base, "options": {**(payload_base.get("options") or {}), **options}}
            try:
                result = run_job(args.api_url, payload, args.poll_interval, args.poll_timeout)
                util = result.get("metrics", {}).get("utilization")
                bins_used = result.get("bins_used")
                runtime_ms = result.get("metrics", {}).get("runtime_ms")
                rows.append({
                    "case_id": case_id,
                    "config_name": name,
                    "utilization": util if util is not None else "",
                    "bins_used": bins_used if bins_used is not None else "",
                    "runtime_ms": runtime_ms if runtime_ms is not None else "",
                    "status": "ok",
                })
            except Exception as e:
                rows.append({
                    "case_id": case_id,
                    "config_name": name,
                    "utilization": "",
                    "bins_used": "",
                    "runtime_ms": "",
                    "status": str(e)[:80],
                })
            time.sleep(0.5)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("case_id,config_name,utilization,bins_used,runtime_ms,status\n")
        for r in rows:
            f.write(f"{r['case_id']},{r['config_name']},{r['utilization']},{r['bins_used']},{r['runtime_ms']},\"{r['status']}\"\n")

    print(f"Wrote {len(rows)} rows to {out_path}")
    # Summary by config (avg utilization when ok)
    by_config = {}
    for r in rows:
        k = r["config_name"]
        if k not in by_config:
            by_config[k] = []
        if r["status"] == "ok" and r["utilization"] != "":
            try:
                by_config[k].append(float(r["utilization"]))
            except ValueError:
                pass
    print("\nAvg utilization by config (when ok):")
    for name, vals in sorted(by_config.items()):
        print(f"  {name}: {sum(vals)/len(vals):.4f}" if vals else f"  {name}: (no data)")


if __name__ == "__main__":
    main()
