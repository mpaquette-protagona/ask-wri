# AskWRI — Research Gaps Feature (Journey 3)

My part of AskWRI. This is the "where is WRI's research thin?" feature.

## What it does (one sentence)

When a researcher asks about a topic, it shows where WRI's work is thin and suggests
where to look next — always backed by real counts and real sources.

## How to explain it

When you ask about a topic, it does three things:

1. **Counts coverage** — how many WRI documents exist on the topic, broken down by region
   and time period, so you can see the thin spots.
2. **Finds what WRI says is still open** — pulls quotes from WRI's own reports where the
   authors name limitations or future research needed.
3. **Points to similar work** — the closest WRI documents you could build on, and the
   method or format they used.

## Why it's different from a basic gaps bot

- **Real counts, not guesses.** The counts come from a tool that counts the actual documents
  in the library (`coverage_stats`), so every number is exact and reproducible. A plain
  chatbot just eyeballs a list and estimates.
- **No fake sources.** Every quote is cited to a real document and page. If the answer isn't
  in WRI's research, it says so instead of making something up.
- **Honest labels.** Every line is tagged so you always know what you're reading:
  - `[Observation]` — a real count / coverage fact
  - `[Evidence]` — a cited quote from a WRI document
  - `[Suggestion]` — a direction the AI proposes (not a WRI finding)

## The honest caveat (we show this on every answer)

It only sees the sample of documents we loaded. So a "gap" might just mean we didn't load
that document, not that WRI never wrote about it. Every answer ends with:

> "Based on N documents in this sample; gaps may reflect the sample, not all of WRI's work."

## What the output looks like

Example question: *"Where are the gaps in WRI's research on Forests?"*

```
## Coverage summary
[Observation] WRI has 6 Forests documents in this sample.
[Observation] By region: Africa 3, Asia 2, Latin America 1, Europe 0, North America 0, Oceania 0.
[Observation] Europe, North America, and Oceania look thin (0 documents each).

## What WRI says is still open
[Evidence] "Further monitoring is needed to track illegal logging at the local level." [1]

## Similar work you could build on
[Evidence] A forest-access study in Central Africa used satellite mapping with field surveys. [2]

## Suggested directions
[Suggestion] Adapt the satellite-mapping method in [2] to a Latin American forest region.

Sources:
[1] Title..., pages 12-13, URL, "..."
[2] Title..., pages 4-6, URL, "..."

Based on 6 documents in this sample; gaps may reflect the sample, not all of WRI's work.
```

## How it's built (for the team)

- Lives in the chat agent (`agent/agent.py`) as the **gaps agent**, one of the sub-agents
  the orchestrator routes to.
- Added one new tool, **`coverage_stats`**, that counts documents from the DynamoDB library
  table by region and time period. The numbers are computed in code, not by the model.
- Rewrote the gaps prompt to follow a fixed method: measure first, then find open questions,
  then find similar work, then label every line Observation / Evidence / Suggestion.
- Gave the gaps agent a bigger search budget (10 vs 5) because gap analysis needs more
  searches than a single question.

## Status

- Deployed to AgentCore (agent version 2, READY).
- Running on a sample of ~52 WRI research PDFs (1997–2026) in S3.
