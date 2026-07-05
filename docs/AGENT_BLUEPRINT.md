# OPC Multi-Agent Blueprint

## Core requirement

OpenAI is used inside the core decision path, not only for report writing. The
workflow is:

1. Data & Finance Agent prepares the opportunity profile and rule-based signals.
   Inside this agent, an AI/NLP tool reads unstructured contract/payment/delivery
   text, extracts business meaning, and updates capacity/funding signals.
2. Risk & Compliance Agent consumes the AI-enriched Data & Finance handoff.
3. Decision & Partner Agent produces the financing, partner, and founder
   decision card.

## Agent responsibilities

| Agent | Input | Agent action | Output | HITL point |
| --- | --- | --- | --- | --- |
| Data & Finance Agent | MotherDuck tables `03_CUSTOMERS`, `04_CONTRACTS`, `06_ORDERS`, `07_INVOICES`, `09_CASHFLOW`, plus KG route context | Join data, calculate readiness, margin, AR, cashflow gap, funding need; call internal AI/NLP tool to infer rollout scale, banking requirement, operational complexity, and risk narrative | Opportunity profile, screening, finance payload, structured AI/NLP reasoning | Only stops for Need Clarification or Hold override |
| Risk & Compliance Agent | AI-enriched screening/finance payload, `13_RISK_RULES`, KG RiskRule/approval routes | Maps signals to risk rules and severity, then verifies them with guardrails | Risk flags and risk level | No routine HITL; handoff continues unless business rules require escalation |
| Decision & Partner Agent | Enriched screening/finance, risk output, credit profile, bank products | Matches financing type, credit case, bank product, then creates decision card | Recommendation, conditions, mitigation, next actions | Founder final approval and external release gate |

## Why AI reasoning is core

The AI/NLP tool output is written back into the Data & Finance handoff before downstream agents:

- `province_count` can force `capacity_risk_flag = true`.
- `operational_complexity = High` can force `feasibility_status = Feasible with Conditions`.
- `bank_service_required_flag = true` can force `funding_need = Required`.
- `cashflow_reasoning` and `risk_narrative` appear in the Decision Card reasons.

For the current live demo, `AI_PROVIDER=groq` uses Groq's OpenAI-compatible
chat API with a Llama model. The same adapter can switch to OpenAI by setting
`AI_PROVIDER=openai` once a valid OpenAI key or contest gateway is available.
If the API call fails, the system falls back to deterministic extraction and
marks the result as `Fallback` so the demo visibly shows whether AI was active.
