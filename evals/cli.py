"""Eval driver CLI: `run` (live matrix) and `retro` (historical baseline).

    python -m evals.cli run   [--models m1,m2] [--workload W] [--run-id ID] [--no-yield]
    python -m evals.cli retro --workload W [--sample N] [--run-id ID]

Config comes from evals/config.yaml (override with --config); flags override
config values. The driver talks to Errand only through MCP.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys

from config import load_config
from corpus import CorpusError, corpus_version, load_corpus

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_DIR = os.path.dirname(_HERE)
_CORPUS_DIR = os.path.join(_HERE, "corpus")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="evals")
    p.add_argument("--config", default=os.path.join(_HERE, "config.yaml"))
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the live model×workload matrix")
    run.add_argument("--models", help="Comma-separated model slugs (overrides config)")
    run.add_argument("--workload", help="Limit the run to one workload")
    run.add_argument("--run-id", help="Resume an existing run id")
    run.add_argument("--no-yield", action="store_true", help="Do not yield to production tasks")

    retro = sub.add_parser("retro", help="Retro-judge historical tasks for a workload")
    retro.add_argument("--workload", required=True)
    retro.add_argument("--sample", type=int, default=10)
    retro.add_argument("--run-id", help="Resume/append to an existing retro run id")
    return p


def _make_client(cfg):
    from mcp_client import ErrandMCPClient  # imported here so tests can run without `mcp`
    return ErrandMCPClient(cfg.mcp_url, cfg.api_key())


async def cmd_run(cfg, args) -> int:
    import runner as runner_mod

    try:
        corpus = load_corpus(_CORPUS_DIR, args.workload)
    except CorpusError as exc:
        print(f"corpus error: {exc}", file=sys.stderr)
        return 2
    if not corpus:
        print("no corpus tasks found", file=sys.stderr)
        return 2

    version, dirty = corpus_version(_REPO_DIR)
    if dirty:
        print(f"WARNING: evals/corpus/ has uncommitted changes — recorded corpus_version={version} is unreliable", file=sys.stderr)

    client = _make_client(cfg)
    run_id = args.run_id
    if not run_id:
        resp = await client.start_eval_run("live", version, cfg.judge_model, driver_host=socket.gethostname())
        run_id = resp["run_id"]
        print(f"started run {run_id} (corpus_version={version})")
    await runner_mod.run_matrix(client, cfg, corpus, run_id, no_yield=args.no_yield)
    print(f"run {run_id} complete")
    return 0


async def cmd_retro(cfg, args) -> int:
    import retro as retro_mod

    try:
        corpus = load_corpus(_CORPUS_DIR, args.workload)
    except CorpusError as exc:
        print(f"corpus error: {exc}", file=sys.stderr)
        return 2
    if not corpus:
        print(f"no corpus for workload '{args.workload}' — author its rubric first", file=sys.stderr)
        return 2
    rubric = corpus[0].rubric

    version, _dirty = corpus_version(_REPO_DIR)
    client = _make_client(cfg)
    run_id = args.run_id
    if not run_id:
        resp = await client.start_eval_run("retro", version, cfg.judge_model, driver_host=socket.gethostname())
        run_id = resp["run_id"]
        print(f"started retro run {run_id}")
    summary = await retro_mod.run_retro(client, cfg, args.workload, args.sample, run_id, rubric)
    await client.finish_eval_run(run_id)
    print(f"retro complete: recorded={summary['recorded']} skipped={len(summary['skipped'])}")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    overrides = {}
    if getattr(args, "models", None):
        overrides["models"] = [m.strip() for m in args.models.split(",") if m.strip()]
    cfg = load_config(args.config, overrides)
    if args.command == "run":
        return asyncio.run(cmd_run(cfg, args))
    if args.command == "retro":
        return asyncio.run(cmd_retro(cfg, args))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
