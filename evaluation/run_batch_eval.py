"""Run the AskWRI batch evaluation against the deployed agent and write a report.

Run from the ask-wri folder (after: python evaluation/build_dataset.py):

    python evaluation/run_batch_eval.py                 # all 23 questions, two batch jobs
    python evaluation/run_batch_eval.py --only q01,q16  # a quick check on a few questions
    python evaluation/run_batch_eval.py --label baseline

What happens:
1. The questions are split into two groups: answerable and unanswerable. Each group gets its own
   batch evaluation job, because a job only reports averages and the two groups want opposite
   things (answer versus decline).
2. For each question the AgentCore SDK calls the deployed agent once, in its own session. Our
   invoker times the call (latency) and reads which documents the agent read (retrieval recall).
3. The SDK waits for the traces to reach CloudWatch, starts the batch job, and waits for it.
4. We fetch the score of every session, join it with latency and recall, and write
   evaluation/results/<run>/ (report.md, sessions.json, summary.json, events.json, insights.json).

This is the only file that uses the batch evaluation SDK, which is in preview: if its API changes,
only this file needs fixing. Tested with bedrock-agentcore 1.25.3 (see evaluation/requirements.txt).

Cost per full run: 23 agent answers, plus one judge model call per evaluator per session
(more for the tool-call evaluators, which score every tool call).
"""

import argparse
import json
import logging
import os
import re
import statistics
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config
from bedrock_agentcore.evaluation import (
    AgentInvokerOutput,
    BatchEvaluationRunConfig,
    BatchEvaluationRunner,
    BatchEvaluatorConfig,
    CloudWatchDataSourceConfig,
    Dataset,
    FileDatasetProvider,
)

HERE = Path(__file__).parent
AGENT_NAME = "askwri_agent"  # the agent's name in Terraform (agent.tf)
ENDPOINT = "DEFAULT"
# A decline: the research agent's fixed "I couldn't find this in the WRI documents..." reply, or the
# orchestrator's own wording of it ("I couldn't find anything on this in WRI's..."). Straight or
# curly apostrophe.
DECLINE = re.compile(r"couldn.?t find", re.I)
# Evaluators where a high score is bad, and ones that are not a score (FailureAnalysis writes 0 for
# "no failures found"; its findings are in the insights)
HIGH_IS_BAD = {"Builtin.Refusal"}
NOT_A_SCORE = {"Builtin.FailureAnalysis"}

# The evaluators of each job (a job takes at most 10)
EVALUATORS = {
    "answerable": [
        "Builtin.GoalSuccessRate",         # session: are the key facts (assertions) in the answer?
        "Builtin.Correctness",             # trace: does the answer match the expected response?
        "Builtin.Faithfulness",            # trace: is the answer backed by the retrieved text?
        "Builtin.Helpfulness",             # trace
        "Builtin.InstructionFollowing",    # trace: citations, format, the prompt's rules
        "Builtin.Refusal",                 # trace: did it refuse a question it could answer?
        "Builtin.ToolSelectionAccuracy",   # tool call
        "Builtin.ToolParameterAccuracy",   # tool call: query and filters given to search_wri
        "Builtin.TrajectoryAnyOrderMatch", # session: was the expected sub-agent called?
        "Builtin.FailureAnalysis",         # session: groups failures into insights
    ],
    "unanswerable": [
        "Builtin.GoalSuccessRate",         # declined / corrected the premise (see the assertions)
        "Builtin.FailureAnalysis",
    ],
}

TARGETS = {  # from OFFLINE_EVALUATION.md (the vision doc targets) and our design
    "recall": 0.75,            # mean retrieval recall on answerable questions, at least
    "latency_s": 60,           # every question, under
    "false_declines": 2,       # answerable questions declined, at most
}

# boto3 gives up after 60 s by default and a long answer can take minutes, so wait up to 15.
# Retries are off: a retry would run the whole agent a second time.
# max_pool_connections: every question runs at once, more than boto3's default pool of 10.
SLOW_CALL_CONFIG = Config(read_timeout=900, retries={"max_attempts": 1, "mode": "standard"},
                          max_pool_connections=50)


# ---- Setup ----

def find_agent(session):
    """Return (ARN, runtime id) of the agent called AGENT_NAME."""
    control = session.client("bedrock-agentcore-control")
    for page in control.get_paginator("list_agent_runtimes").paginate():
        for runtime in page["agentRuntimes"]:
            if runtime["agentRuntimeName"] == AGENT_NAME:
                return runtime["agentRuntimeArn"], runtime["agentRuntimeId"]
    raise RuntimeError(f"No AgentCore agent named {AGENT_NAME} in {session.region_name}. "
                       "Pass --region (or set AWS_REGION) to the region you deployed to.")


def git_version():
    """Short commit of the ask-wri repo, with "-dirty" if there are uncommitted changes."""
    def git(*args):
        return subprocess.run(["git", "-C", str(HERE.parent), *args], capture_output=True,
                              text=True).stdout.strip()
    sha = git("rev-parse", "--short", "HEAD") or "unknown"
    return sha + ("-dirty" if git("status", "--porcelain", "--", "agent", "terraform") else "")


def chat_model():
    """The chat model the agent code uses (read from agent/agent.py)."""
    match = re.search(r'^CHAT_MODEL\s*=\s*"([^"]+)"', (HERE.parent / "agent" / "agent.py").read_text(), re.M)
    return match.group(1) if match else "unknown"


def job_name(label, group, stamp):
    """Batch job names allow letters, digits and _ only, start with a letter, max 48 characters."""
    name = re.sub(r"[^a-zA-Z0-9_]", "_", f"askwri_{group}_{stamp}_{label}")  # label last: it may be cut
    return name[:48]


# ---- The invoker: calls the agent, and records latency and the documents it read ----

class Recorder:
    """Calls the deployed agent and remembers what happened in each session (thread-safe)."""

    def __init__(self, client, agent_arn):
        self.client, self.agent_arn = client, agent_arn
        self.sessions = {}
        self.lock = threading.Lock()

    def __call__(self, invoker_input):
        payload = invoker_input.payload
        if isinstance(payload, str):  # the same payload the chat page sends ("" = every language)
            payload = {"prompt": payload, "language": ""}
        record = {"error": None}
        started = time.monotonic()
        try:
            resp = self.client.invoke_agent_runtime(agentRuntimeArn=self.agent_arn,
                                                    runtimeSessionId=invoker_input.session_id,
                                                    payload=json.dumps(payload))
            reply = json.loads(resp["response"].read())
            answer = reply.get("answer", "")
            record.update(answer=answer, declined=bool(DECLINE.search(answer)),
                          doc_ids=sorted({r["doc_id"] for r in reply.get("read", [])}))
            return AgentInvokerOutput(agent_output=answer)
        except Exception as e:  # the SDK records the scenario as failed; we keep the reason too
            record["error"] = str(e)[:500]
            raise
        finally:
            record["latency_s"] = round(time.monotonic() - started, 1)
            with self.lock:
                self.sessions[invoker_input.session_id] = record


# ---- Running one job ----

def run_job(group, scenarios, args, agent_arn, runtime_id, label, stamp):
    session = boto3.Session(region_name=args.region)
    recorder = Recorder(session.client("bedrock-agentcore", config=SLOW_CALL_CONFIG), agent_arn)
    config = BatchEvaluationRunConfig(
        batch_evaluation_name=job_name(label, group, stamp),
        description=f"AskWRI {group} questions, {label}",
        evaluator_config=BatchEvaluatorConfig(evaluator_ids=EVALUATORS[group]),
        data_source=CloudWatchDataSourceConfig(
            service_names=[f"{AGENT_NAME}.{ENDPOINT}"],
            log_group_names=[f"/aws/bedrock-agentcore/runtimes/{runtime_id}-{ENDPOINT}"],
            ingestion_delay_seconds=args.ingestion_delay,
        ),
        max_concurrent_scenarios=args.concurrency or len(scenarios),
        polling_timeout_seconds=3600,
        polling_interval_seconds=10,
        kms_key_arn=args.kms_key_arn,
        tags={"project": "askwri", "run": label},
    )
    runner = BatchEvaluationRunner(region=session.region_name)
    print(f"[{group}] invoking the agent for {len(scenarios)} questions...")
    result = runner.run_dataset_evaluation(config=config, dataset=Dataset(scenarios=scenarios),
                                           agent_invoker=recorder)
    print(f"[{group}] job {result.batch_evaluation_id}: {result.status}")

    events = []
    if result.output_data_config:
        for attempt in range(6):  # the per-session results can land a little after the job ends
            try:
                events = runner.fetch_evaluation_events(result)
                break
            except LookupError:
                time.sleep(15)
    return result, recorder.sessions, events


# ---- Turning results into numbers ----

def attributes(event):
    return event.get("attributes", event)


def scenario_of(session_id):
    """The SDK names sessions "<scenario_id>-<uuid4>"; a uuid4 is 36 characters."""
    return session_id[:-37]


def group_of(scenario):
    meta = scenario.metadata or {}
    return meta["journey"] if meta.get("answerable") else meta.get("unanswerable_type") or "unanswerable"


def build_rows(scenarios, recorded, events):
    """One row per question: latency, recall, declined, and the mean score of each evaluator."""
    by_id = {s.scenario_id: s for s in scenarios}
    rows = {}
    for session_id, record in recorded.items():
        scenario = by_id[scenario_of(session_id)]
        expected = set((scenario.metadata or {}).get("expected_doc_ids", []))
        found = set(record.get("doc_ids", []))
        rows[session_id] = {
            "id": scenario.scenario_id, "group": group_of(scenario), "session_id": session_id,
            "answerable": bool((scenario.metadata or {}).get("answerable")),
            "latency_s": record["latency_s"], "error": record["error"],
            "declined": record.get("declined"),
            "recall": round(len(found & expected) / len(expected), 2) if expected and not record["error"] else None,
            "doc_ids": sorted(found), "missing_doc_ids": sorted(expected - found),
            "answer": record.get("answer", ""), "scores": {}, "explanations": {},
        }
    scores = {}  # (session, evaluator) -> scores (tool-call evaluators give one per tool call)
    for event in events:
        attrs = attributes(event)
        session_id, name = attrs.get("session.id"), attrs.get("gen_ai.evaluation.name")
        value = attrs.get("gen_ai.evaluation.score.value")
        if session_id not in rows or not name or name in NOT_A_SCORE:
            continue
        if value is not None:
            scores.setdefault((session_id, name), []).append(float(value))
        explanation = attrs.get("gen_ai.evaluation.explanation")
        if explanation:
            rows[session_id]["explanations"].setdefault(name, []).append(
                {"score": value, "label": attrs.get("gen_ai.evaluation.score.label"), "text": explanation})
    for (session_id, name), values in scores.items():
        rows[session_id]["scores"][name] = round(statistics.mean(values), 3)
    return sorted(rows.values(), key=lambda r: r["id"])


def mean(values):
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), 3) if values else None


def summarize(rows, jobs):
    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    declines_expected = [r for r in unanswerable if r["group"] != "false_premise"]
    premises = [r for r in unanswerable if r["group"] == "false_premise"]
    passed = lambda r: (r["scores"].get("Builtin.GoalSuccessRate") or 0) >= 0.5  # noqa: E731
    latencies = [r["latency_s"] for r in rows if not r["error"]]
    checks = {
        "recall": {"value": mean([r["recall"] for r in answerable]), "target": f">= {TARGETS['recall']}"},
        "max_latency_s": {"value": max(latencies) if latencies else None,
                          "target": f"< {TARGETS['latency_s']}"},
        "false_declines": {"value": sum(bool(r["declined"]) for r in answerable),
                           "target": f"<= {TARGETS['false_declines']} of {len(answerable)}"},
        "declined_correctly": {"value": sum(passed(r) for r in declines_expected),
                               "target": f"{len(declines_expected)} of {len(declines_expected)}"},
        "premises_corrected": {"value": sum(passed(r) for r in premises),
                               "target": f"{len(premises)} of {len(premises)}"},
    }
    checks["recall"]["pass"] = checks["recall"]["value"] is not None and checks["recall"]["value"] >= TARGETS["recall"]
    checks["max_latency_s"]["pass"] = bool(latencies) and max(latencies) < TARGETS["latency_s"]
    checks["false_declines"]["pass"] = checks["false_declines"]["value"] <= TARGETS["false_declines"]
    checks["declined_correctly"]["pass"] = checks["declined_correctly"]["value"] == len(declines_expected)
    checks["premises_corrected"]["pass"] = checks["premises_corrected"]["value"] == len(premises)

    groups = {}
    for row in rows:
        groups.setdefault(row["group"], []).append(row)
    by_group = {}
    for group, members in groups.items():
        names = sorted({n for r in members for n in r["scores"]})
        by_group[group] = {"questions": len(members),
                           "mean_latency_s": mean([r["latency_s"] for r in members if not r["error"]]),
                           "recall": mean([r["recall"] for r in members]),
                           "scores": {n: mean([r["scores"].get(n) for r in members]) for n in names}}
    warnings = []
    unscored = [r["id"] for r in rows if not r["error"] and not r["scores"]]
    if unscored:
        warnings.append(f"No scores for {', '.join(unscored)}: the job may have looked before their traces "
                        "arrived. Rerun with a longer --ingestion-delay.")
    for group, job in jobs.items():
        if job.get("ignored") or job.get("failed"):
            warnings.append(f"Job {group}: {job.get('ignored') or 0} sessions ignored, "
                            f"{job.get('failed') or 0} failed (see summary.json).")
    return {"checks": checks, "by_group": by_group, "jobs": jobs, "warnings": warnings,
            "errors": [{"id": r["id"], "error": r["error"]} for r in rows if r["error"]]}


# ---- Report ----

GROUP_ORDER = ["qa", "briefing", "gap", "off_topic", "in_domain_missing", "false_premise"]
SHORT = {"Builtin.GoalSuccessRate": "Goal", "Builtin.Correctness": "Correct",
         "Builtin.Faithfulness": "Faithful", "Builtin.Helpfulness": "Helpful",
         "Builtin.InstructionFollowing": "Instr", "Builtin.Refusal": "Refusal",
         "Builtin.ToolSelectionAccuracy": "ToolSel", "Builtin.ToolParameterAccuracy": "ToolParam",
         "Builtin.TrajectoryAnyOrderMatch": "Route"}


def fmt(value):
    return "–" if value is None else (f"{value:.2f}" if isinstance(value, float) else str(value))


def write_report(path, info, summary, rows, insights):
    lines = [f"# AskWRI batch evaluation: {info['label']}", "",
             f"- Run: `{info['run']}`, {info['started']}",
             f"- Agent code: `{info['git']}`, chat model `{info['model']}`",
             f"- Questions: {len(rows)}"]
    for group, job in summary["jobs"].items():
        lines.append(f"- Job `{group}`: `{job['id']}` {job['status']}, sessions completed "
                     f"{job['completed']}, failed {job['failed']}, ignored {job.get('ignored')}")
    for warning in summary.get("warnings", []):
        lines.append(f"- ⚠️ {warning}")
    lines += ["", "## Targets", "", "| Check | Value | Target | Pass |", "|---|---|---|---|"]
    for name, check in summary["checks"].items():
        lines.append(f"| {name} | {fmt(check['value'])} | {check['target']} | {'✅' if check['pass'] else '❌'} |")
    lines += ["", "`false_declines` counts answerable questions whose answer says it \"couldn't find\" the "
              "answer. `declined_correctly` and `premises_corrected` count sessions with "
              "GoalSuccessRate ≥ 0.5.", ""]

    names = [n for n in SHORT if any(n in g["scores"] for g in summary["by_group"].values())]
    lines += ["## Scores by group (mean, 0–1)", "",
              "Higher is better, except Refusal (lower is better: 0 means it answered).", "",
              "| Group | n | Latency s | Recall | " + " | ".join(SHORT[n] for n in names) + " |",
              "|---|---|---|---|" + "---|" * len(names)]
    for group in sorted(summary["by_group"], key=lambda g: GROUP_ORDER.index(g) if g in GROUP_ORDER else 99):
        g = summary["by_group"][group]
        lines.append(f"| {group} | {g['questions']} | {fmt(g['mean_latency_s'])} | {fmt(g['recall'])} | "
                     + " | ".join(fmt(g["scores"].get(n)) for n in names) + " |")

    lines += ["", "## Per question", "",
              "| Id | Group | Latency s | Recall | Declined | " + " | ".join(SHORT[n] for n in names) + " |",
              "|---|---|---|---|---|" + "---|" * len(names)]
    for r in rows:
        lines.append(f"| {r['id']} | {r['group']} | {fmt(r['latency_s'])} | {fmt(r['recall'])} | "
                     f"{'yes' if r['declined'] else 'no'} | " + " | ".join(fmt(r["scores"].get(n)) for n in names) + " |")

    def bad(name, score):
        return score is not None and (float(score) >= 0.5 if name in HIGH_IS_BAD else float(score) < 0.5)

    low = [(r, n, e) for r in rows for n, es in r["explanations"].items() for e in es if bad(n, e["score"])]
    if low:
        lines += ["", "## Failed scores and the judge's reason", "",
                  "Below 0.5, or for Refusal 0.5 and above (a refusal of an answerable question).", ""]
        for r, n, e in low:
            text = " ".join(e["text"].split())[:400]
            lines.append(f"- **{r['id']} {SHORT.get(n, n)}** ({fmt(float(e['score']))}): {text}")
    missing = [r for r in rows if r["missing_doc_ids"]]
    if missing:
        lines += ["", "## Expected documents not read", ""]
        lines += [f"- **{r['id']}**: {', '.join(r['missing_doc_ids'])}" for r in missing]
    if insights:
        lines += ["", "## Failure analysis insights", ""]
        for group, items in insights.items():
            for item in items:
                lines.append(f"- **[{group}] {item.get('name')}** ({item.get('affected_session_count')} sessions): "
                             f"{item.get('description')}")
                for cause in item.get("root_causes") or []:
                    lines.append(f"  - {cause.get('name')}: {cause.get('explanation')} "
                                 f"Suggested fix: {cause.get('suggested_fix')}")
    if summary["errors"]:
        lines += ["", "## Invocation errors", ""]
        lines += [f"- **{e['id']}**: {e['error']}" for e in summary["errors"]]
    lines += ["", "## Judge check", "",
              "Hand-grade about 5 sessions (pick a mix of high and low scores) and note how often you agree "
              "with the judge here.", ""]
    path.write_text("\n".join(lines))


# ---- Main ----

def main():
    parser = argparse.ArgumentParser(description="Batch-evaluate the deployed AskWRI agent")
    parser.add_argument("--dataset", default=str(HERE / "dataset.json"))
    parser.add_argument("--only", default="", help="comma-separated question ids, e.g. q01,q16")
    parser.add_argument("--label", default="", help="name for this run (default: the git commit)")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION"),
                        help="default: AWS_REGION, else your AWS profile's region (like the chat page)")
    parser.add_argument("--concurrency", type=int, default=0,
                        help="agent calls at once, per job (default: every question at once)")
    # Spans reached CloudWatch within ~5 s of a session ending (measured on 4 sessions), so the SDK's
    # default of 180 s is mostly idle. Skipped sessions are reported, so a too-short wait is visible.
    parser.add_argument("--ingestion-delay", type=int, default=30,
                        help="seconds to wait for traces to reach CloudWatch (default 30)")
    parser.add_argument("--kms-key-arn", default=None, help="encrypt the job's data with this key")
    parser.add_argument("--rebuild", default="", metavar="RESULTS_FOLDER",
                        help="don't run anything: recompute the report of an earlier run from its files")
    args = parser.parse_args()
    if args.rebuild:
        return rebuild(Path(args.rebuild), args.dataset)
    # Show the SDK's progress (ingestion wait, job status every 10 s); a full run takes about 4.5 minutes
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("bedrock_agentcore.evaluation").setLevel(logging.INFO)

    dataset = FileDatasetProvider(args.dataset).get_dataset()
    scenarios = dataset.scenarios
    if args.only:
        wanted = set(args.only.split(","))
        scenarios = [s for s in scenarios if s.scenario_id in wanted]
        if not scenarios:
            raise SystemExit(f"None of {sorted(wanted)} are in {args.dataset}")
    groups = {"answerable": [s for s in scenarios if (s.metadata or {}).get("answerable")],
              "unanswerable": [s for s in scenarios if not (s.metadata or {}).get("answerable")]}
    groups = {g: s for g, s in groups.items() if s}

    session = boto3.Session(region_name=args.region)
    agent_arn, runtime_id = find_agent(session)
    version = git_version()
    label = args.label or version
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run = f"{stamp}-{re.sub(r'[^a-zA-Z0-9_.-]', '_', label)}"
    out = HERE / "results" / run
    out.mkdir(parents=True)
    print(f"Run {run}: agent {agent_arn}, {len(scenarios)} questions, jobs: {', '.join(groups)}")

    # The two jobs run at the same time, so the waits (ingestion, scoring) overlap
    with ThreadPoolExecutor(max_workers=len(groups)) as pool:
        futures = {g: pool.submit(run_job, g, s, args, agent_arn, runtime_id, label, stamp)
                   for g, s in groups.items()}
        outcomes = {g: f.result() for g, f in futures.items()}

    recorded, events, jobs, insights = {}, [], {}, {}
    for group, (result, sessions, job_events) in outcomes.items():
        recorded.update(sessions)
        events += job_events
        er = result.evaluation_results
        jobs[group] = {"id": result.batch_evaluation_id, "status": result.status,
                       "submitted": len(groups[group]) - len(result.agent_invocation_failures),
                       "completed": er.number_of_sessions_completed if er else None,
                       "failed": er.number_of_sessions_failed if er else None,
                       "ignored": er.number_of_sessions_ignored if er else None,
                       "evaluator_averages": {s.evaluator_id: s.statistics.average_score if s.statistics else None
                                              for s in (er.evaluator_summaries or [])} if er else {},
                       "error_details": result.error_details,
                       "invocation_failures": [f.model_dump() for f in result.agent_invocation_failures]}
        insights[group] = [i.model_dump(mode="json") for i in result.insight_results or []]

    info = {"run": run, "label": label, "git": version, "model": chat_model(),
            "started": stamp, "agent_arn": agent_arn, "questions": [s.scenario_id for s in scenarios]}
    (out / "events.json").write_text(json.dumps(events, indent=2, ensure_ascii=False, default=str))
    (out / "insights.json").write_text(json.dumps(insights, indent=2, ensure_ascii=False))
    (out / "recorded.json").write_text(json.dumps(recorded, indent=2, ensure_ascii=False))
    finish(out, info, jobs, scenarios, recorded, events, insights)


def finish(out, info, jobs, scenarios, recorded, events, insights):
    """Score, summarize and write the report (also used by --rebuild)."""
    rows = build_rows(scenarios, recorded, events)
    summary = summarize(rows, jobs)
    (out / "summary.json").write_text(json.dumps({"info": info, **summary}, indent=2))
    (out / "sessions.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    write_report(out / "report.md", info, summary, rows, insights)

    print(f"\nReport: {out / 'report.md'}")
    for name, check in summary["checks"].items():
        print(f"  {'PASS' if check['pass'] else 'FAIL'}  {name}: {fmt(check['value'])} (target {check['target']})")
    for warning in summary["warnings"]:
        print(f"  WARNING  {warning}")
    if not events:
        print("  No per-session scores were fetched; see the job statuses in summary.json.")


def rebuild(out, dataset_path):
    """Recompute sessions.json, summary.json and report.md from a run's saved files."""
    saved = json.loads((out / "summary.json").read_text())
    if (out / "recorded.json").exists():
        recorded = json.loads((out / "recorded.json").read_text())
    else:  # runs from before recorded.json existed: the same fields are in sessions.json
        keep = ("answer", "doc_ids", "latency_s", "error")
        recorded = {r["session_id"]: {k: r.get(k) for k in keep}
                    for r in json.loads((out / "sessions.json").read_text())}
        for record in recorded.values():
            record["declined"] = bool(DECLINE.search(record["answer"] or ""))
        (out / "recorded.json").write_text(json.dumps(recorded, indent=2, ensure_ascii=False))
    wanted = set(saved["info"]["questions"])
    scenarios = [s for s in FileDatasetProvider(dataset_path).get_dataset().scenarios if s.scenario_id in wanted]
    finish(out, saved["info"], saved["jobs"], scenarios, recorded,
           json.loads((out / "events.json").read_text()), json.loads((out / "insights.json").read_text()))


if __name__ == "__main__":
    main()
