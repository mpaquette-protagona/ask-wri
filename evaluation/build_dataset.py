"""Turn questions.json (our test questions) into dataset.json (the AgentCore Evaluations format).

Run from the ask-wri folder:  python evaluation/build_dataset.py

Each question becomes one scenario with one turn. The ground truth the evaluators read:
- assertions           -> Builtin.GoalSuccessRate (did the answer do what we expect?)
- expected_response    -> Builtin.Correctness (does the answer match the key facts?)
- expected_trajectory  -> Builtin.TrajectoryAnyOrderMatch (were the right sub-agent and tools called?)
Everything else (journey, expected documents) goes in metadata, which only our own script reads.
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).parent

# The tools each kind of question should use: the sub-agent the orchestrator sends it to, and the
# sub-agent's first tool (the trajectory evaluator sees the sub-agents' tool calls too). It is
# scored with TrajectoryAnyOrderMatch, so extra calls (more searches, charts, follow-ups) are fine.
TRAJECTORY = {"qa": ["research_agent", "search_wri"], "briefing": ["research_agent", "search_wri"],
              "gap": ["gaps_agent", "list_documents"]}

# Extra expectations that depend on the kind of question, on top of its key facts
JOURNEY_ASSERTIONS = {
    "briefing": ["The answer is a briefing with a summary, cited key findings and a list of sources."],
    "gap": ["The answer names specific areas where WRI's research on the topic is thin or missing."],
}
DECLINE_ASSERTIONS = [
    "The agent says the WRI documents it has access to don't cover this question.",
    "The agent doesn't answer from outside knowledge and doesn't invent figures or findings.",
]


def premise_assertions(correction):
    fact = re.sub(r"\s*\([^)]*\)\.?$", ".", correction)  # drop the "(doc-id, ...)" at the end
    return [
        "The agent points out that the question's premise is wrong.",
        f"The agent states the correct fact from the WRI documents: {fact}",
        "The agent doesn't explain or justify the false premise as if it were true.",
    ]


def to_scenario(question):
    turn = {"input": question["question"]}  # plain text: the invoker builds the agent's payload
    scenario = {
        "scenario_id": question["id"],
        "turns": [turn],
        "metadata": {
            "journey": question["journey"],
            "answerable": question["answerable"],
            "unanswerable_type": question.get("unanswerable_type"),
            "expected_doc_ids": question["expected_doc_ids"],
        },
    }
    if question["answerable"]:
        facts = question["key_facts"]
        scenario["assertions"] = [f"The answer states: {f}" for f in facts]
        scenario["assertions"] += JOURNEY_ASSERTIONS.get(question["journey"], [])
        turn["expected_response"] = " ".join(f.rstrip(".") + "." for f in facts)
        scenario["expected_trajectory"] = TRAJECTORY[question["journey"]]
    elif question.get("unanswerable_type") == "false_premise":
        scenario["assertions"] = premise_assertions(question["premise_correction"])
    else:
        scenario["assertions"] = DECLINE_ASSERTIONS
    return scenario


def main():
    questions = json.loads((HERE / "questions.json").read_text())
    scenarios = [to_scenario(q) for q in questions]
    (HERE / "dataset.json").write_text(json.dumps({"scenarios": scenarios}, indent=2, ensure_ascii=False))
    answerable = sum(q["answerable"] for q in questions)
    print(f"Wrote evaluation/dataset.json: {len(scenarios)} scenarios "
          f"({answerable} answerable, {len(scenarios) - answerable} unanswerable)")


if __name__ == "__main__":
    main()
