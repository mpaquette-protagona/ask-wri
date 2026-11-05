"""Compare two batch evaluation runs (for example the baseline and a prompt change).

Run from the ask-wri folder:

    python evaluation/compare_runs.py evaluation/results/<before> evaluation/results/<after>

Prints the targets, the mean scores by group, and the questions whose scores dropped, before and
after. Only questions that are in both runs are compared.
"""

import json
import sys
from pathlib import Path

DROP = 0.25  # a score that falls by at least this much is listed as a regression


def load(folder):
    folder = Path(folder)
    summary = json.loads((folder / "summary.json").read_text())
    rows = {r["id"]: r for r in json.loads((folder / "sessions.json").read_text())}
    return summary, rows


def fmt(value):
    return "–" if value is None else (f"{value:.2f}" if isinstance(value, float) else str(value))


def delta(before, after):
    if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
        return ""
    change = after - before
    if not change:
        return "0"
    return f"{change:+d}" if isinstance(change, int) else f"{change:+.2f}"


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    (s1, r1), (s2, r2) = load(sys.argv[1]), load(sys.argv[2])
    shared = sorted(set(r1) & set(r2))
    i1, i2 = s1["info"], s2["info"]
    print(f"# {i1['label']} → {i2['label']}\n")
    print(f"- Before: `{i1['run']}` (code `{i1['git']}`, model `{i1['model']}`)")
    print(f"- After: `{i2['run']}` (code `{i2['git']}`, model `{i2['model']}`)")
    print(f"- Questions in both runs: {len(shared)}")
    if set(r1) ^ set(r2):
        print(f"- Only in one run (ignored): {', '.join(sorted(set(r1) ^ set(r2)))}")
        print("- The targets below cover each run's own questions, so they may not be comparable.")

    print("\n## Targets\n\n| Check | Before | After | Change |\n|---|---|---|---|")
    for name, check in s1["checks"].items():
        after = s2["checks"].get(name, {})
        mark = lambda c: ("✅ " if c.get("pass") else "❌ ") + fmt(c.get("value"))  # noqa: E731
        print(f"| {name} | {mark(check)} | {mark(after)} | {delta(check.get('value'), after.get('value'))} |")

    print("\n## Mean scores by group\n\n| Group | Evaluator | Before | After | Change |\n|---|---|---|---|---|")
    for group in sorted(set(s1["by_group"]) & set(s2["by_group"])):
        g1, g2 = s1["by_group"][group], s2["by_group"][group]
        metrics = {"latency_s": (g1["mean_latency_s"], g2["mean_latency_s"]),
                   "recall": (g1["recall"], g2["recall"])}
        for name in sorted(set(g1["scores"]) | set(g2["scores"])):
            metrics[name.replace("Builtin.", "")] = (g1["scores"].get(name), g2["scores"].get(name))
        for name, (before, after) in metrics.items():
            if before is not None or after is not None:
                print(f"| {group} | {name} | {fmt(before)} | {fmt(after)} | {delta(before, after)} |")

    print(f"\n## Questions that got worse (score down by {DROP} or more, or newly declined)\n")
    worse = []
    for qid in shared:
        a, b = r1[qid], r2[qid]
        for name in sorted(set(a["scores"]) & set(b["scores"])):
            if a["scores"][name] - b["scores"][name] >= DROP:
                worse.append(f"- **{qid}** {name.replace('Builtin.', '')}: "
                             f"{fmt(a['scores'][name])} → {fmt(b['scores'][name])}")
        if a.get("recall") is not None and b.get("recall") is not None and a["recall"] - b["recall"] >= DROP:
            worse.append(f"- **{qid}** recall: {fmt(a['recall'])} → {fmt(b['recall'])}")
        if a["answerable"] and b.get("declined") and not a.get("declined"):
            worse.append(f"- **{qid}**: now declined")
    print("\n".join(worse) if worse else "None.")


if __name__ == "__main__":
    main()
