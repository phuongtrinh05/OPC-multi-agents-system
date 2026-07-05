"""
OPC Opportunity Agent Orchestrator
==================================
Coordinates the business agents required by the MIS Talent 2026 case:

1. Data & Finance Agent
2. Risk & Compliance Agent
3. Decision & Partner Agent

AI/NLP reasoning is a tool action inside Data & Finance Agent, not a fourth
business agent. Each API response includes `agent_outputs` and `agent_trace`
for the three core agents only.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from agents.data_finance_agent import DataFinanceAgent
from agents.decision_partner_agent import DecisionPartnerAgent
from agents.ai_reasoning_tool import AIReasoningTool
from agents.risk_compliance_agent import RiskComplianceAgent
from agents.shared import TARGET_OPPORTUNITY_STATUSES, as_float, row, text
from connector import get_connector


TABLE_NAMES = [
    "02_OPC_PROFILE",
    "03_CUSTOMERS",
    "04_CONTRACTS",
    "05_PRODUCTS",
    "06_ORDERS",
    "07_INVOICES",
    "08_BANK_TXN",
    "09_CASHFLOW",
    "10_CREDIT_PROFILE",
    "11_BANK_PRODUCTS",
    "13_RISK_RULES",
    "14_ALERTS",
]


def _load_tables() -> dict[str, pd.DataFrame]:
    conn = get_connector()
    return {name: conn.read_table(name, 10_000) for name in TABLE_NAMES}


def list_opportunities() -> list[dict[str, Any]]:
    tables = _load_tables()
    contracts = tables["04_CONTRACTS"]
    customers = tables["03_CUSTOMERS"]
    opportunities = contracts.copy()

    result = []
    for _, contract in opportunities.iterrows():
        customer = row(customers, "customer_id", contract.get("customer_id")) or {}
        status = text(contract.get("status"))
        is_core_opportunity = status in TARGET_OPPORTUNITY_STATUSES
        result.append(
            {
                "contract_id": text(contract.get("contract_id")),
                "customer_id": text(contract.get("customer_id")),
                "customer_name": text(customer.get("customer_name")),
                "customer_type": text(customer.get("customer_type")),
                "status": status,
                "is_core_opportunity": is_core_opportunity,
                "demo_scope": (
                    "Core opportunity"
                    if is_core_opportunity
                    else "Demo/test contract"
                ),
                "contract_value": as_float(contract.get("contract_value"), 0.0),
                "payment_terms": text(contract.get("payment_terms")),
                "description": text(contract.get("description")),
            }
        )
    return sorted(
        result,
        key=lambda item: (
            0 if item["is_core_opportunity"] else 1,
            item["contract_id"],
        ),
    )


def evaluate_opportunity(
    contract_id: str,
    evaluation_date: date | None = None,
) -> dict[str, Any]:
    evaluation_date = evaluation_date or date.today()
    tables = _load_tables()

    data_finance_agent = DataFinanceAgent()
    ai_tool = AIReasoningTool()
    risk_agent = RiskComplianceAgent()
    decision_agent = DecisionPartnerAgent()

    data_finance_output, context = data_finance_agent.run(
        tables,
        contract_id,
        evaluation_date,
    )
    ai_output = ai_tool.run(data_finance_output)
    _apply_ai_reasoning_tool(data_finance_output, ai_output)

    risk_output = risk_agent.run(tables, data_finance_output)
    decision_output = decision_agent.run(tables, data_finance_output, risk_output)

    old_flag_ids = [
        flag["rule_id"]
        for flag in risk_output["outputs"]["risk"]["applicable_risk_flags"]
    ]
    confidence_score = decision_output["outputs"]["partner"].get("confidence_score")
    risk_output = risk_agent.add_confidence_rule(
        tables,
        risk_output,
        confidence_score,
    )
    new_flag_ids = [
        flag["rule_id"]
        for flag in risk_output["outputs"]["risk"]["applicable_risk_flags"]
    ]
    if old_flag_ids != new_flag_ids:
        decision_output = decision_agent.run(tables, data_finance_output, risk_output)

    profile = {
        "contract_id": contract_id,
        "evaluation_date": evaluation_date.isoformat(),
        "source_tables": TABLE_NAMES,
        "opportunity_profile": data_finance_output["outputs"]["opportunity_profile"],
        "screening": data_finance_output["outputs"]["screening"],
        "finance": data_finance_output["outputs"]["finance"],
        "openai_reasoning": ai_output["outputs"]["openai_reasoning"],
        "risk": risk_output["outputs"]["risk"],
        "financing": decision_output["outputs"]["financing"],
        "partner": decision_output["outputs"]["partner"],
        "decision_card": decision_output["outputs"]["decision_card"],
        "agent_outputs": {
            "data_finance_agent": data_finance_output,
            "risk_compliance_agent": risk_output,
            "decision_partner_agent": decision_output,
        },
    }
    profile["agent_trace"] = _agent_trace(profile["agent_outputs"])
    return profile


def run_data_finance_step(
    contract_id: str,
    evaluation_date: date | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    evaluation_date = evaluation_date or date.today()
    tables = _load_tables()
    data_finance_output, _context = DataFinanceAgent().run_intake_screening(
        tables,
        contract_id,
        evaluation_date,
    )
    profile = _workflow_profile(
        contract_id,
        evaluation_date,
        {"data_finance_agent": data_finance_output},
    )
    return profile, data_finance_output


def run_ai_reasoning_step(
    contract_id: str,
    data_finance_output: dict[str, Any],
    evaluation_date: date | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    evaluation_date = evaluation_date or date.today()
    tables = _load_tables()
    data_finance_output = DataFinanceAgent().run_finance_after_shortlist(
        tables,
        data_finance_output,
        evaluation_date,
    )
    ai_output = AIReasoningTool().run(data_finance_output)
    _apply_ai_reasoning_tool(data_finance_output, ai_output)
    profile = _workflow_profile(
        contract_id,
        evaluation_date,
        {"data_finance_agent": data_finance_output},
    )
    return profile, ai_output


def run_risk_step(
    contract_id: str,
    data_finance_output: dict[str, Any],
    evaluation_date: date | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    evaluation_date = evaluation_date or date.today()
    tables = _load_tables()
    risk_output = RiskComplianceAgent().run(tables, data_finance_output)
    profile = _workflow_profile(
        contract_id,
        evaluation_date,
        {
            "data_finance_agent": data_finance_output,
            "risk_compliance_agent": risk_output,
        },
    )
    return profile, risk_output


def run_decision_step(
    contract_id: str,
    data_finance_output: dict[str, Any],
    risk_output: dict[str, Any],
    evaluation_date: date | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    evaluation_date = evaluation_date or date.today()
    tables = _load_tables()
    risk_agent = RiskComplianceAgent()
    decision_agent = DecisionPartnerAgent()
    decision_output = decision_agent.run(tables, data_finance_output, risk_output)

    old_flag_ids = [
        flag["rule_id"]
        for flag in risk_output["outputs"]["risk"]["applicable_risk_flags"]
    ]
    confidence_score = decision_output["outputs"]["partner"].get("confidence_score")
    risk_output = risk_agent.add_confidence_rule(tables, risk_output, confidence_score)
    new_flag_ids = [
        flag["rule_id"]
        for flag in risk_output["outputs"]["risk"]["applicable_risk_flags"]
    ]
    if old_flag_ids != new_flag_ids:
        decision_output = decision_agent.run(tables, data_finance_output, risk_output)

    profile = _workflow_profile(
        contract_id,
        evaluation_date,
        {
            "data_finance_agent": data_finance_output,
            "risk_compliance_agent": risk_output,
            "decision_partner_agent": decision_output,
        },
    )
    return profile, risk_output, decision_output


def _workflow_profile(
    contract_id: str,
    evaluation_date: date,
    agent_outputs: dict[str, Any],
) -> dict[str, Any]:
    data_finance_output = agent_outputs.get("data_finance_agent")
    risk_output = agent_outputs.get("risk_compliance_agent")
    decision_output = agent_outputs.get("decision_partner_agent")
    ai_output = None
    if data_finance_output:
        ai_output = data_finance_output.get("tool_outputs", {}).get(
            "ai_reasoning_tool"
        )

    profile: dict[str, Any] = {
        "contract_id": contract_id,
        "evaluation_date": evaluation_date.isoformat(),
        "source_tables": TABLE_NAMES,
        "agent_outputs": agent_outputs,
        "agent_trace": _agent_trace(agent_outputs),
        "workflow_complete": decision_output is not None,
    }
    if data_finance_output:
        profile["opportunity_profile"] = data_finance_output["outputs"][
            "opportunity_profile"
        ]
        profile["screening"] = data_finance_output["outputs"]["screening"]
        if "finance" in data_finance_output["outputs"]:
            profile["finance"] = data_finance_output["outputs"]["finance"]
    if ai_output:
        profile["openai_reasoning"] = ai_output["outputs"]["openai_reasoning"]
    if risk_output:
        profile["risk"] = risk_output["outputs"]["risk"]
    if decision_output:
        profile["financing"] = decision_output["outputs"]["financing"]
        profile["partner"] = decision_output["outputs"]["partner"]
        profile["decision_card"] = decision_output["outputs"]["decision_card"]
    return profile


def _apply_ai_reasoning_tool(
    data_finance_output: dict[str, Any],
    ai_output: dict[str, Any],
) -> None:
    reasoning = ai_output["outputs"]["openai_reasoning"]
    screening = data_finance_output["outputs"]["screening"]
    finance = data_finance_output["outputs"]["finance"]

    provider = reasoning.get("provider", "openai")
    screening["openai_reasoning_status"] = (
        f"{provider.title()} Active" if reasoning.get("ai_used") else "Fallback"
    )
    screening["openai_operational_complexity"] = reasoning.get(
        "operational_complexity"
    )
    screening["openai_confidence"] = reasoning.get("confidence")
    screening["openai_risk_narrative"] = reasoning.get("risk_narrative")
    screening["openai_recommended_focus"] = reasoning.get("recommended_focus", [])

    province_count = reasoning.get("province_count")
    if province_count is not None:
        screening["province_count"] = province_count

    high_complexity = reasoning.get("operational_complexity") == "High"
    if high_complexity or (province_count is not None and province_count >= 10):
        screening["capacity_risk_flag"] = True
        if screening["feasibility_status"] == "Feasible":
            screening["feasibility_status"] = "Feasible with Conditions"
        if screening["preliminary_screening_result"] == "Shortlist for Deep Assessment":
            screening["preliminary_screening_result"] = "Conditional Shortlist"
        note = "OpenAI: rollout scale/complexity requires implementation capacity review."
        if note not in screening["gateway_flags"]:
            screening["gateway_flags"].append(note)

    finance["openai_cashflow_reasoning"] = reasoning.get("cashflow_reasoning")
    finance["openai_bank_service_required_flag"] = reasoning.get(
        "bank_service_required_flag"
    )
    if reasoning.get("bank_service_required_flag"):
        finance["bank_service_required_flag"] = True
        finance["funding_need"] = "Required"

    data_finance_output.setdefault("tool_outputs", {})[
        "ai_reasoning_tool"
    ] = ai_output
    data_finance_output["handoff_to"] = "Risk & Compliance Agent"
    data_finance_output["handoff_payload"] = {
        "low_margin_flag": screening["low_margin_flag"],
        "cashflow_gap_flag": finance["cashflow_gap_flag"],
        "delivery_delay_risk_flag": screening["delivery_delay_risk_flag"],
        "funding_need": finance["funding_need"],
        "funding_gap": finance.get("funding_gap"),
        "financial_needs": finance.get("financial_needs", []),
        "openai_status": screening["openai_reasoning_status"],
        "openai_operational_complexity": screening[
            "openai_operational_complexity"
        ],
        "openai_bank_service_required_flag": finance[
            "openai_bank_service_required_flag"
        ],
        "ai_nlp_tool": ai_output["handoff_payload"],
    }


def _agent_trace(agent_outputs: dict[str, Any]) -> list[dict[str, Any]]:
    trace = []
    for key, output in agent_outputs.items():
        trace.append(
            {
                "agent_key": key,
                "agent_name": output["agent_name"],
                "role": output["role"],
                "inputs": output["inputs"],
                "actions": output["actions"],
                "handoff_to": output["handoff_to"],
                "handoff_payload": output["handoff_payload"],
            }
        )
    return trace
