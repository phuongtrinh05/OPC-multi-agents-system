from __future__ import annotations

import json
from typing import Any

import pandas as pd

from agents.ai_provider import AgenticAIClient
from agents.knowledge_base import (
    compact_guardrails_for,
    compact_rules_for,
)
from agents.knowledge_graph import compact_graph_for, sql_plan_for_agent
from agents.shared import records, risk_rule, text


class RiskComplianceAgent:
    name = "Risk & Compliance Agent"
    role = (
        "Convert finance/screening flags into applicable risk rules, severity, "
        "required action, and final contract-level risk_level."
    )

    def run(
        self,
        tables: dict[str, pd.DataFrame],
        data_finance_output: dict[str, Any],
    ) -> dict[str, Any]:
        risk_rules = tables["13_RISK_RULES"]
        handoff = data_finance_output["handoff_payload"]
        deterministic_rule_ids = self._mandatory_rule_ids(handoff)
        fallback_reasoning = self._fallback_reasoning(risk_rules, deterministic_rule_ids)
        ai_reasoning = self._run_ai_risk_reasoning(
            risk_rules,
            data_finance_output,
            deterministic_rule_ids,
            fallback_reasoning,
        )

        applicable_rule_ids = self._guarded_rule_ids(
            risk_rules,
            deterministic_rule_ids,
            ai_reasoning.get("applicable_rule_ids", []),
            data_finance_output,
        )
        verification = self._post_output_verification(
            risk_rules,
            deterministic_rule_ids,
            ai_reasoning,
            applicable_rule_ids,
        )
        applicable_flags = [risk_rule(risk_rules, rule_id) for rule_id in applicable_rule_ids]

        risk = {
            "risk_level": self._risk_level(applicable_flags),
            "applicable_risk_flags": applicable_flags,
            "agent_reasoning": {
                "ai_used": ai_reasoning.get("ai_used", False),
                "provider": ai_reasoning.get("provider"),
                "mode": ai_reasoning.get("mode"),
                "summary": self._list(ai_reasoning.get("reasoning_summary"))[:5],
                "rule_interpretation": self._list(
                    ai_reasoning.get("rule_interpretation")
                )[:6],
                "evidence_used": self._list(ai_reasoning.get("evidence_used"))[:6],
                "missing_info": self._list(ai_reasoning.get("missing_info"))[:4],
                "confidence": ai_reasoning.get("confidence", 0.0),
                "ai_proposed_rule_ids": self._list(
                    ai_reasoning.get("applicable_rule_ids")
                ),
                "guardrail_required_rule_ids": deterministic_rule_ids,
                "final_rule_ids": applicable_rule_ids,
                "prevention_guardrails": [
                    "Prompt restricts Risk Agent to supplied opportunity/finance/rule evidence.",
                    "AI must cite field=value evidence and list missing_info.",
                    "Python deterministic mandatory rules are authoritative.",
                ],
                "post_output_verification": verification,
                "guardrail_note": (
                    "Python guardrail validates AI proposed rules against mandatory "
                    "business flags and the 13_RISK_RULES catalog."
                ),
                "error": ai_reasoning.get("friendly_error")
                or ai_reasoning.get("error"),
                "friendly_error": ai_reasoning.get("friendly_error"),
                "prompt_bytes": ai_reasoning.get("prompt_bytes"),
            },
        }
        risk_memory = self._risk_memory(risk, data_finance_output)
        return {
            "agent_name": self.name,
            "role": self.role,
            "inputs": [
                "opportunity_knowledge_graph.agent_view: Risk & Compliance Agent",
                "OpenAI-enriched Data & Finance handoff payload",
                "13_RISK_RULES",
            ],
            "actions": [
                "Resolve Risk & Compliance graph view to identify permitted risk entities, SQL tools, and rule mappings.",
                "Read the OpenAI-enriched opportunity profile, finance flags, and 13_RISK_RULES catalog.",
                "Ask the configured AI provider to propose applicable risk rules with evidence.",
                "Validate AI rule selection with deterministic guardrails for mandatory business flags.",
                "Aggregate the validated rule severities into final risk_level.",
            ],
            "knowledge_graph_context": compact_graph_for(self.name),
            "sql_tool_plan": sql_plan_for_agent(
                self.name,
                contract_id=text(
                    data_finance_output["outputs"]["opportunity_profile"]["linked_keys"].get(
                        "contract_id"
                    )
                ),
            ),
            "outputs": {"risk": risk, "risk_memory": risk_memory},
            "handoff_to": "Decision & Partner Agent",
            "handoff_payload": {
                "risk_level": risk["risk_level"],
                "applicable_risk_flags": [
                    item["rule_id"] for item in applicable_flags
                ],
                "risk_reasoning_summary": risk["agent_reasoning"]["summary"],
                "risk_evidence_used": risk["agent_reasoning"]["evidence_used"],
            },
        }

    def add_confidence_rule(
        self,
        tables: dict[str, pd.DataFrame],
        risk_output: dict[str, Any],
        confidence_score: float | None,
    ) -> dict[str, Any]:
        if confidence_score is None or confidence_score >= 0.65:
            return risk_output

        rr006 = risk_rule(tables["13_RISK_RULES"], "RR-006")
        flags = risk_output["outputs"]["risk"]["applicable_risk_flags"]
        if not any(flag["rule_id"] == "RR-006" for flag in flags):
            flags.append(rr006)
        risk_output["outputs"]["risk"]["risk_level"] = self._risk_level(flags)
        risk_output["handoff_payload"]["risk_level"] = risk_output["outputs"]["risk"][
            "risk_level"
        ]
        risk_output["handoff_payload"]["applicable_risk_flags"] = [
            item["rule_id"] for item in flags
        ]
        risk_output["actions"].append(
            "Guardrail added RR-006 because banking recommendation confidence_score < 0.65."
        )
        reasoning = risk_output["outputs"]["risk"].setdefault("agent_reasoning", {})
        reasoning.setdefault("guardrail_required_rule_ids", []).append("RR-006")
        reasoning["final_rule_ids"] = [item["rule_id"] for item in flags]
        reasoning.setdefault("rule_interpretation", []).append(
            "RR-006 added after partner matching because confidence_score < 0.65."
        )
        risk_output["outputs"]["risk_memory"] = self._risk_memory(
            risk_output["outputs"]["risk"]
        )
        return risk_output

    def _mandatory_rule_ids(self, handoff: dict[str, Any]) -> list[str]:
        rule_ids = []
        funding_gap = handoff.get("funding_gap", {})
        financial_need_types = {
            text(need.get("type")) for need in funding_gap.get("needs", []) or []
        }
        if handoff.get("cashflow_gap_flag") or "working_capital" in financial_need_types:
            rule_ids.append("RR-002")
        if handoff.get("low_margin_flag"):
            rule_ids.append("RR-003")
        if handoff.get("delivery_delay_risk_flag"):
            rule_ids.append("RR-007")
        return rule_ids

    def _risk_memory(
        self,
        risk: dict[str, Any],
        data_finance_output: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        flags = risk.get("applicable_risk_flags", [])
        finance_memory = (
            (data_finance_output or {}).get("outputs", {}).get("finance_memory", {})
        )
        contract_id = text(finance_memory.get("contract", {}).get("contract_id"))
        months = finance_memory.get("cashflow_summary", {}).get(
            "months_below_reserve", []
        )
        alerts = [
            self._alert_from_rule(flag, contract_id, months)
            for flag in flags
        ]
        blocking_approvals = [
            {
                "approval_id": f"APR-{text(flag.get('rule_id')).replace('RR-', '')}",
                "rule": flag.get("rule_id"),
                "reason": flag.get("required_action")
                or flag.get("trigger_condition")
                or "Founder confirmation required.",
                "blocking": True,
                "status": "Pending",
            }
            for flag in flags
            if text(flag.get("rule_id")) == "RR-001"
        ]
        return {
            "risk_level": risk.get("risk_level"),
            "risk_score": self._risk_score(risk.get("risk_level"), flags),
            "alerts": alerts,
            "blocking_approvals": blocking_approvals,
            "proceed_allowed": True,
            "triggered_rules": [flag.get("rule_id") for flag in flags],
            "recommended_actions": [
                flag.get("required_action")
                for flag in flags
                if flag.get("required_action")
            ],
        }

    def _alert_from_rule(
        self,
        flag: dict[str, Any],
        contract_id: str,
        months: list[Any],
    ) -> dict[str, Any]:
        rule_id = text(flag.get("rule_id"))
        alert_type = {
            "RR-001": "Transaction anomaly",
            "RR-002": "Cashflow shortage",
            "RR-003": "Margin pressure",
            "RR-006": "Low recommendation confidence",
            "RR-007": "Delivery delay risk",
        }.get(rule_id, "Risk rule triggered")
        related = {
            "RR-002": [text(month) for month in months if text(month)],
            "RR-003": [contract_id] if contract_id else [],
        }.get(rule_id, [])
        return {
            "alert_id": f"AL-{rule_id.replace('RR-', '')}",
            "severity": flag.get("severity") or "Medium",
            "type": alert_type,
            "related": related,
            "description": flag.get("trigger_condition")
            or flag.get("description")
            or flag.get("required_action"),
            "action": flag.get("required_action"),
        }

    def _risk_score(self, risk_level: str | None, flags: list[dict[str, Any]]) -> int:
        base = {"Low": 25, "Medium": 55, "High": 75}.get(text(risk_level), 40)
        return min(100, base + max(0, len(flags) - 1) * 5)

    def _run_ai_risk_reasoning(
        self,
        risk_rules: pd.DataFrame,
        data_finance_output: dict[str, Any],
        deterministic_rule_ids: list[str],
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "opportunity_profile": data_finance_output["outputs"].get(
                "opportunity_profile"
            ),
            "screening": data_finance_output["outputs"].get("screening"),
            "finance": data_finance_output["outputs"].get("finance"),
            "handoff_payload": data_finance_output.get("handoff_payload"),
            "risk_rule_catalog": records(risk_rules),
            "knowledge_graph_rule_catalog": compact_rules_for(
                "Risk & Compliance Agent"
            ),
            "opportunity_knowledge_graph": compact_graph_for(
                "Risk & Compliance Agent"
            ),
            "sql_tool_plan": sql_plan_for_agent(
                "Risk & Compliance Agent",
                contract_id=text(
                    data_finance_output["outputs"]["opportunity_profile"][
                        "linked_keys"
                    ].get("contract_id")
                ),
            ),
            "agent_guardrails": compact_guardrails_for("Risk & Compliance Agent"),
            "mandatory_guardrail_rule_ids": deterministic_rule_ids,
        }
        system_prompt = (
            "You are OPC's Risk & Compliance supporting agent. Your job is not to "
            "approve or reject a contract. Your job is to read Finance Memory, "
            "risk-rule catalog, knowledge-graph rule ownership, and guardrails; "
            "then identify which risk/compliance rules are supported by evidence. "
            "Use banking/SME-finance domain logic: cash reserve breach, margin "
            "pressure, suspicious transaction, missing document, and low partner "
            "confidence are different risks and must not be merged. Prevention "
            "guardrail: use only supplied fields, cite evidence as field=value, "
            "never invent missing transactions/documents/products, and list gaps "
            "in missing_info. Verification guardrail: after drafting the output, "
            "check every proposed rule_id exists in 13_RISK_RULES and is backed by "
            "a cited field. Return auditable summaries only, not private chain-of-thought."
        )
        task_prompt = (
            "Return JSON only with keys: applicable_rule_ids (array of rule_id), "
            "reasoning_summary (array of 3-5 Vietnamese bullets), "
            "rule_interpretation (array mapping rule_id to why it applies or does not), "
            "evidence_used (array of field=value strings), missing_info (array), "
            "confidence (number 0-1). INPUT_JSON:\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )
        return AgenticAIClient(provider_env="RISK_AI_PROVIDER").complete_json(
            system_prompt, task_prompt, fallback
        )

    def _guarded_rule_ids(
        self,
        risk_rules: pd.DataFrame,
        mandatory_rule_ids: list[str],
        ai_rule_ids: Any,
        data_finance_output: dict[str, Any],
    ) -> list[str]:
        known_rule_ids = {text(value) for value in risk_rules.get("rule_id", [])}
        supported_rule_ids = self._source_supported_rule_ids(data_finance_output)
        final_ids = []
        for rule_id in [*self._list(ai_rule_ids), *mandatory_rule_ids]:
            rule_id = text(rule_id)
            if (
                rule_id in known_rule_ids
                and rule_id in supported_rule_ids
                and rule_id not in final_ids
            ):
                final_ids.append(rule_id)
        return final_ids

    def _source_supported_rule_ids(self, data_finance_output: dict[str, Any]) -> set[str]:
        outputs = data_finance_output.get("outputs", {})
        screening = outputs.get("screening", {})
        finance = outputs.get("finance", {})
        handoff = data_finance_output.get("handoff_payload", {})
        supported = set()
        if handoff.get("cashflow_gap_flag") or finance.get("cashflow_gap_flag"):
            supported.add("RR-002")
        if handoff.get("low_margin_flag") or screening.get("low_margin_flag"):
            supported.add("RR-003")
        if handoff.get("delivery_delay_risk_flag") or screening.get("delivery_delay_risk_flag"):
            supported.add("RR-007")
        return supported

    def _post_output_verification(
        self,
        risk_rules: pd.DataFrame,
        mandatory_rule_ids: list[str],
        ai_reasoning: dict[str, Any],
        final_rule_ids: list[str],
    ) -> dict[str, Any]:
        known_rule_ids = {text(value) for value in risk_rules.get("rule_id", [])}
        proposed_ids = self._list(ai_reasoning.get("applicable_rule_ids"))
        unknown_ids = [rule_id for rule_id in proposed_ids if text(rule_id) not in known_rule_ids]
        missing_mandatory = [
            rule_id for rule_id in mandatory_rule_ids if rule_id not in final_rule_ids
        ]
        checks = [
            {
                "name": "ai_rule_ids_exist_in_13_RISK_RULES",
                "passed": not unknown_ids,
                "details": f"unknown={', '.join(map(text, unknown_ids)) or 'none'}",
            },
            {
                "name": "mandatory_source_flags_preserved",
                "passed": not missing_mandatory,
                "details": f"missing={', '.join(missing_mandatory) or 'none'}",
            },
            {
                "name": "final_rules_are_catalog_rules",
                "passed": all(rule_id in known_rule_ids for rule_id in final_rule_ids),
                "details": f"final={', '.join(final_rule_ids) or 'none'}",
            },
            {
                "name": "evidence_or_fallback_present",
                "passed": bool(self._list(ai_reasoning.get("evidence_used")))
                or ai_reasoning.get("mode") == "fallback",
                "details": "evidence_used checked after AI output.",
            },
        ]
        corrective_actions = []
        if unknown_ids:
            corrective_actions.append(
                "Dropped AI-proposed rule IDs not found in 13_RISK_RULES."
            )
        if mandatory_rule_ids:
            corrective_actions.append(
                "Re-applied mandatory source-field risk rules after AI output."
            )
        return {
            "stage": "after_ai_output",
            "passed": all(item["passed"] for item in checks),
            "checks": checks,
            "corrective_actions": corrective_actions
            or ["AI risk output accepted after rule/evidence verification."],
        }

    def _fallback_reasoning(
        self, risk_rules: pd.DataFrame, deterministic_rule_ids: list[str]
    ) -> dict[str, Any]:
        flags = [risk_rule(risk_rules, rule_id) for rule_id in deterministic_rule_ids]
        return {
            "applicable_rule_ids": deterministic_rule_ids,
            "reasoning_summary": [
                "Fallback guardrail selected risk rules from deterministic business flags.",
                f"Validated risk_level = {self._risk_level(flags)} from rule severity.",
            ],
            "rule_interpretation": [
                f"{flag['rule_id']}: {flag.get('required_action')}"
                for flag in flags
            ],
            "evidence_used": [
                f"mandatory_rule_ids={', '.join(deterministic_rule_ids) or 'none'}"
            ],
            "missing_info": [],
            "confidence": 0.45,
        }

    def _list(self, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple) or isinstance(value, set):
            return list(value)
        return [value]

    def _risk_level(self, applicable_flags: list[dict[str, Any]]) -> str:
        severities = {flag.get("severity") for flag in applicable_flags}
        if "Critical" in severities or "High" in severities:
            return "High"
        if "Medium" in severities:
            return "Medium"
        return "Low"
