# Evaluating the agent

This folder tests the **deployed** AskWRI agent on 23 fixed questions and writes a report: did it
find the right documents, answer correctly, decline what it should, and how fast. Scoring is done
by [AgentCore batch evaluation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/batch-evaluations.html)
(an AI judge). A full run takes about **4.5 minutes**.

The usual loop: run it, change something (a prompt, the model, retrieval), redeploy, run it again,
and compare the two runs.

**Contents:** [Your first run](#your-first-run-about-10-minutes) ·
[Reading the report](#reading-the-report) · [The baseline](#the-baseline) ·
[After you change the agent](#after-you-change-the-agent) ·
[The questions](#the-questions) · [How it works](#how-it-works) ·
[Troubleshooting](#troubleshooting) · [Files](#files)

---

## Your first run (about 10 minutes)

**1. Check you have what it needs.**
- The agent is deployed (the [Quick start](../README.md#quick-start-deploy-it-into-your-own-aws-account)
  is done) **with tracing on**: `terraform/agent.tf` starts the agent with `opentelemetry-instrument`.
  If you deployed before that change, run `python agent/build_zip.py` and `terraform apply` again.
- **CloudWatch Transaction Search** is on in the account (it stores the traces the judge reads).
  Check: `aws xray get-trace-segment-destination --region us-east-1` (your agent's region) should
  show `"Destination": "CloudWatchLogs"` and `"Status": "ACTIVE"`. If not, turn it on in the CloudWatch console under
  *Application Signals (APM) → Transaction search → Enable Transaction Search*, with "ingest spans
  as structured logs" ticked ([AWS guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html)),
  then wait a few minutes.
- Your AWS user or role may call: `bedrock-agentcore:ListAgentRuntimes`,
  `bedrock-agentcore:InvokeAgentRuntime`, `bedrock-agentcore:StartBatchEvaluation`,
  `bedrock-agentcore:GetBatchEvaluation` and `logs:GetLogEvents`.

**2. Set your AWS profile and region** in the terminal, as in Quick start step A (the agent is in
`us-east-1` unless you deployed elsewhere). Run every command below from the **repo root**.
If `AWS_REGION` is also set in your terminal (`echo $AWS_REGION`), it wins over
`AWS_DEFAULT_REGION`: set it to the same region, or add `--region us-east-1` to the commands.

**3. Install the packages** (once):

```bash
pip install -r requirements.txt -r evaluation/requirements.txt
```

**4. Try two questions first** (about 2 minutes, a few cents). This checks your setup:

```bash
python evaluation/run_batch_eval.py --only q01,q16 --label first-try
```

You should see two jobs end in `COMPLETED`, then a few `PASS`/`FAIL` lines and the path to a
report. If you get an error, see [Troubleshooting](#troubleshooting).

**5. Run all 23 questions** (about 4.5 minutes):

```bash
python evaluation/run_batch_eval.py --label my-baseline
```

**6. Open the report:** `evaluation/results/<time>-my-baseline/report.md`. The next section explains it.

---

## Reading the report

`report.md` has these parts, top to bottom:

**Targets.** Pass/fail checks against our goals:

| Check | Target | What it means |
|---|---|---|
| `recall` | ≥ 0.75 | Share of the expected documents the agent actually read (vision doc target) |
| `max_latency_s` | < 60 | The slowest question, in seconds (vision doc target: every question under 60 s) |
| `false_declines` | ≤ 2 of 15 | Answerable questions where the agent said it "couldn't find" the answer |
| `declined_correctly` | all | Off-topic and missing-topic questions the agent declined |
| `premises_corrected` | all | False-premise questions where the agent said the premise is wrong and gave the right fact |

**Scores by group / Per question.** The judge's scores, 0 to 1, higher is better, except
**Refusal** (0 means it answered; high is bad). Column names:

| Column | Evaluator | Question it answers |
|---|---|---|
| Goal | GoalSuccessRate | Did the answer do everything the question's assertions expect? (the main score) |
| Correct | Correctness | Does the answer match the expected key facts? |
| Faithful | Faithfulness | Is everything in the answer backed by the retrieved text? |
| Helpful | Helpfulness | Would a user find it useful? |
| Instr | InstructionFollowing | Did it follow the prompt's rules (citations, format)? |
| Refusal | Refusal | Did it refuse a question it could answer? |
| ToolSel / ToolParam | ToolSelectionAccuracy / ToolParameterAccuracy | Right tool, right arguments (scored per tool call) |
| Route | TrajectoryAnyOrderMatch | Did it use the expected sub-agent and tools? |

**Failed scores and the judge's reason.** Every failed score with the judge's explanation. Read
these first when a number is low: they usually say exactly what went wrong.

**Expected documents not read.** Questions where retrieval missed a document.

**Failure analysis insights.** The FailureAnalysis evaluator groups the failures of all sessions
into patterns, with a root cause and a suggested fix. (It writes 0 when a session had no failure,
so it is left out of the score tables.)

**What to keep in mind**
- **One run is a sample.** The agent's answers vary: in our tests, a question that failed passed
  when rerun. Run 2–3 times before you trust a number or a change.
- **The judge can be wrong.** For each important run, read about 5 sessions yourself (a mix of high
  and low scores, in `sessions.json`) and note whether you agree.
- **Briefing and gap questions are graded strictly:** GoalSuccessRate is 0 unless *every* key fact
  appears, so a decent briefing that misses one fact scores 0.
- The AgentCore console (*Evaluations → Batch evaluations*) shows the same jobs. Its averages mix
  all question kinds and count FailureAnalysis as a score, so use `report.md` for decisions.

---

## The baseline

[`baselines/2026-11-05-before-fixes/`](baselines/2026-11-05-before-fixes/report.md) is our first
full run, of the agent as deployed on 5 November 2026 (commit `27959dc` plus the tracing changes).
It is the "before" that later runs are compared with. The account ID is replaced with
`<ACCOUNT_ID>`.

| | Result | Target |
|---|---|---|
| Retrieval recall | 0.97 | ≥ 0.75 ✅ |
| Off-topic and missing-topic questions declined | 5 of 5 | all ✅ |
| Routing (TrajectoryAnyOrderMatch) | 0.93 | |
| Tool parameter accuracy (151 tool calls) | 0.91 | |
| GoalSuccessRate, answerable questions | 0.27 (4 of 15 passed) | |
| Answerable questions wrongly declined | 3 of 15 | ≤ 2 ❌ |
| False premises corrected | 1 of 3 | all ❌ |
| Slowest question | 66 s (3 over 60 s) | < 60 s ❌ |

**What it found.** Retrieval, routing and declining work well, and the agent never answered from
outside knowledge. Most failures (7 of the 11 failed answerable questions) have one cause: **the
sub-agents' answers get lost.** `research_agent` and `gaps_agent` in `agent/agent.py` return
`str(Agent(...)(request))`, which is only the text of the sub-agent's *last* message. The prompt
has the sub-agent write its answer and *then* call `suggest_followups`, so the last message is
empty or "I've added three follow-up questions". The orchestrator receives nothing, retries, and
tells the user it couldn't find an answer. FailureAnalysis found the same pattern on its own. The
retries also make briefing and gap questions slow. Fixing this is the next step; it was not fixed
when the baseline was taken.

---

## After you change the agent

1. Change the code, then redeploy: `python agent/build_zip.py`, then `terraform apply` in
   `terraform/`.
2. Run the evaluation with a label that says what changed:
   ```bash
   python evaluation/run_batch_eval.py --label fix-subagent-output
   ```
3. Compare with the baseline (or any earlier run):
   ```bash
   python evaluation/compare_runs.py evaluation/baselines/2026-11-05-before-fixes evaluation/results/<time>-fix-subagent-output
   ```
   It prints the targets before and after, the mean scores by question kind, and every question
   that got worse.
4. If the new run should become the reference, copy its `report.md`, `summary.json` and
   `sessions.json` into a new folder under `baselines/`, replacing your account ID:
   ```bash
   mkdir -p evaluation/baselines/<date>-<what>
   for f in report.md summary.json sessions.json; do
     sed "s/$(aws sts get-caller-identity --query Account --output text)/<ACCOUNT_ID>/g" \
       evaluation/results/<run>/$f > evaluation/baselines/<date>-<what>/$f
   done
   ```

Runs in `results/` are not committed (they hold your account ID, full answers and every judge
output). Only `baselines/` is.

---

## The questions

[`questions.json`](questions.json) holds 23 questions about the **6 documents currently ingested**
(the carbon management, energy efficiency (EN and CN), climate finance and carbon pricing briefings,
the China-US dialogue summary and the CCG year in review):

| Kind (`journey` / `unanswerable_type`) | Count | What a good answer does |
|---|---|---|
| `qa` | 9 | States the key facts, with citations (q07 is in Chinese) |
| `briefing` | 3 | A briefing with a summary, cited key findings and sources |
| `gap` | 3 | Names where WRI's research on the topic is thin |
| `off_topic` | 2 | Declines (not about WRI research at all) |
| `in_domain_missing` | 3 | Declines (a WRI topic, but not in the loaded documents) |
| `false_premise` | 3 | Says the premise is wrong and states the correct fact |

Each question has these fields:

| Field | Used for |
|---|---|
| `id`, `question`, `journey` | Identity, the text sent to the agent, and the kind |
| `answerable`, `unanswerable_type` | Which job it goes in, and what a good answer does |
| `expected_doc_ids` | Retrieval recall (the documents it should read) |
| `key_facts` | The judge's assertions and expected response (answerable questions only) |
| `evidence` | The quotes the key facts come from (for people; not used by the scripts) |
| `premise_correction` | The true fact a false-premise answer must state (false-premise questions only) |

**To add or change a question:** edit `questions.json`, then run
`python evaluation/build_dataset.py`, which rewrites `dataset.json`. Commit both files. Check that
each fact is really in the documents (quote it in `evidence`), and that each document id exists:
the ids are the PDF file names, lowercase, without `.pdf` (for example
`2024-carbon-management-briefing-en`).

**If you ingest more documents:** an "unanswerable" question may become answerable. q17 (ocean
acidification) and q21 (water use in India) are close to `briefing-us-ocean-based-carbon-removal`
and `cost-benefit-analysis-solar-irrigation-pumps-rajasthan`, which are listed in
`docs_to_ingest.txt` but not ingested yet.

---

## How it works

```
questions.json --build_dataset.py--> dataset.json --run_batch_eval.py--> results/<run>/report.md
                                                          |
                     1. call the agent for every question at once (AgentCore SDK)
                        - our code times each call and reads which documents it used
                     2. wait 30 s for the traces to reach CloudWatch
                     3. start 2 batch evaluation jobs: the judge scores each session
                     4. fetch every score, join with latency and recall, write the report
```

- The questions go into **two jobs**, answerable and unanswerable, because a job only reports
  averages and the two groups want opposite things (answer versus decline). The jobs run at the
  same time.
- **Evaluators:** the answerable job runs GoalSuccessRate, Correctness, Faithfulness, Helpfulness,
  InstructionFollowing, Refusal, ToolSelectionAccuracy, ToolParameterAccuracy,
  TrajectoryAnyOrderMatch and FailureAnalysis (a job allows at most 10). The unanswerable job runs
  GoalSuccessRate and FailureAnalysis.
- **What the judge checks** comes from `dataset.json`, built from each question:
  - `assertions`: one per key fact ("The answer states: ..."), plus "is a briefing" or "names
    gaps" for those kinds, or "declines" / "corrects the premise" for unanswerable questions.
  - `expected_response`: the key facts joined, for Correctness.
  - `expected_trajectory`: `research_agent` + `search_wri`, or `gaps_agent` + `list_documents`.
- **Recall and latency are not judged by AI.** The script reads the agent's reply (`read` lists
  every section the agent read) and times the call.
- The batch evaluation SDK is in **preview**, so its version is pinned in `requirements.txt` and
  only `run_batch_eval.py` uses it. If the SDK changes, only that file needs fixing.
- **Cost of a full run:** 23 agent answers, plus judge model calls: one per evaluator per session,
  and one per tool call for the two tool evaluators (about 150 tool calls in the baseline).

**Options** of `run_batch_eval.py`:

| Option | Default | Use |
|---|---|---|
| `--only q01,q16` | all | Run some questions only |
| `--label NAME` | the git commit | Name of the run (in the folder and job names) |
| `--region` | `AWS_REGION`, else your profile's region | Where the agent is deployed |
| `--concurrency N` | every question at once | Lower it (for example 5) if Bedrock throttles |
| `--ingestion-delay S` | 30 | Raise it if the report warns that sessions have no scores |
| `--kms-key-arn ARN` | AWS-owned key | Encrypt the job's data with your own KMS key |
| `--rebuild FOLDER` | | Recompute a run's report from its saved files, without calling AWS |

---

## Troubleshooting

| What you see | What to do |
|---|---|
| `No AgentCore agent named askwri_agent in us-west-2` | Wrong region: pass `--region us-east-1`. A set `AWS_REGION` wins over `AWS_DEFAULT_REGION`, so check both. |
| `AccessDeniedException` | Your role lacks one of the permissions in step 1 of the first run. |
| The report warns `No scores for q..` | The judge looked before the traces arrived: rerun with `--ingestion-delay 90`. If every session has no scores, check Transaction Search (step 1) and that the agent was deployed with `opentelemetry-instrument`. |
| `ThrottlingException`, or many invocation errors at the end of the report | Too many questions at once for your Bedrock quota: use `--concurrency 5`. |
| `TimeoutError` or `RuntimeError: ... FAILED` | Look the job up in the AgentCore console (*Evaluations → Batch evaluations*) for its error, then rerun. |
| A question's latency is far above the others | Normal for briefings and gap questions (40–65 s); see the baseline. |

---

## Files

```
evaluation/
  README.md            this guide
  questions.json       the test questions and expected answers (edit this one)
  build_dataset.py     questions.json -> dataset.json
  dataset.json         the questions in the AgentCore dataset format (generated; committed so runs are repeatable)
  run_batch_eval.py    calls the agent, runs the batch evaluation jobs, writes results/<run>/
  compare_runs.py      compares two runs (or a run and a baseline)
  requirements.txt     the pinned AgentCore SDK version
  baselines/           reference runs, committed (report.md, summary.json, sessions.json)
  results/             every run you make, not committed
```

Each run folder in `results/` has: `report.md` (start here), `summary.json` (targets and averages),
`sessions.json` (one entry per question: answer, scores, the judge's reasons), `events.json` (every
raw judge score), `insights.json` (FailureAnalysis findings) and `recorded.json` (what the agent
returned).
