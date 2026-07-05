from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
AGENT_ALIASES = {
    "AI Reasoning Agent": "Data & Finance Agent",
    "OpenAI Reasoning Agent": "Data & Finance Agent",
    "AI/NLP Reasoning Tool": "Data & Finance Agent",
    "Finance Monitor + AI/NLP Reasoning Agent": "Data & Finance Agent",
}


@lru_cache(maxsize=1)
def load_rule_catalog() -> dict[str, Any]:
    return _load_json("rule_catalog.json")


@lru_cache(maxsize=1)
def load_agent_guardrails() -> dict[str, Any]:
    return _load_json("agent_guardrails.json")


def _load_json(file_name: str) -> dict[str, Any]:
    path = KNOWLEDGE_DIR / file_name
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def compact_rules_for(agent_name: str) -> list[dict[str, Any]]:
    agent_name = AGENT_ALIASES.get(agent_name, agent_name)
    rules = load_rule_catalog().get("rules", [])
    selected = [
        rule for rule in rules
        if rule.get("owner_agent") in {agent_name, "Orchestrator"}
    ]
    return [
        {
            "rule_id": rule.get("rule_id"),
            "name": rule.get("name"),
            "sheet_rule_id": rule.get("sheet_rule_id"),
            "inputs": rule.get("inputs"),
            "condition": rule.get("condition"),
            "output": rule.get("output"),
            "evidence_required": rule.get("evidence_required"),
        }
        for rule in selected
    ]


def compact_guardrails_for(agent_name: str) -> dict[str, Any]:
    agent_name = AGENT_ALIASES.get(agent_name, agent_name)
    guardrails = load_agent_guardrails()
    return {
        "global_guardrails": guardrails.get("global_guardrails", []),
        "agent_specific_guardrails": guardrails.get(
            "agent_specific_guardrails", {}
        ).get(agent_name, []),
        "required_ai_output_fields": guardrails.get("required_ai_output_fields", {}),
    }
