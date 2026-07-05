from __future__ import annotations

import json
from typing import Any

import pandas as pd

from agents.ai_provider import AgenticAIClient
from agents.knowledge_base import (
    compact_rules_for,
)
from agents.knowledge_graph import compact_graph_for, sql_plan_for_agent
from agents.shared import as_float, records, row, segment_matches, text


class DecisionPartnerAgent:
    name = "Decision & Partner Agent"
    role = (
        "Translate funding need into financing type, match existing credit case, "
        "compare partner products, and produce the founder-facing Decision Card."
    )

    def run(
        self,
        tables: dict[str, pd.DataFrame],
        data_finance_output: dict[str, Any],
        risk_output: dict[str, Any],
    ) -> dict[str, Any]:
        opportunity_profile = data_finance_output["outputs"]["opportunity_profile"]
        screening = data_finance_output["outputs"]["screening"]
        finance = data_finance_output["outputs"]["finance"]
        finance_memory = data_finance_output["outputs"].get("finance_memory", {})
        risk = risk_output["outputs"]["risk"]
        risk_memory = risk_output["outputs"].get("risk_memory", {})
        contract = opportunity_profile["contract"]
        customer = opportunity_profile["customer"]

        funding_gap = finance.get("funding_gap") or finance_memory.get("funding_gap", {})
        financing_type = self._financing_need_type(
            finance["funding_need"],
            contract.get("payment_terms"),
            funding_gap,
        )
        credit_match = self._match_credit_case(
            tables["10_CREDIT_PROFILE"],
            contract.get("contract_id"),
            financing_type,
            finance["total_open_ar"],
            as_float(contract.get("contract_value"), 0.0) or 0.0,
            as_float(contract.get("gross_margin"), 0.0) or 0.0,
            self._primary_required_amount(funding_gap),
        )
        partner_match = self._match_bank_products(
            tables["11_BANK_PRODUCTS"],
            financing_type,
            credit_match.get("requested_amount"),
            customer,
        )
        deterministic_recommendation = self._recommendation(
            risk["risk_level"],
            partner_match["banking_fit_hint"],
            credit_match.get("eligibility_score"),
        )
        ai_decision = self._run_ai_decision_reasoning(
            tables,
            opportunity_profile,
            screening,
            finance,
            finance_memory,
            risk,
            risk_memory,
            financing_type,
            credit_match,
            partner_match,
            deterministic_recommendation,
        )
        recommendation = self._guarded_recommendation(
            deterministic_recommendation,
            ai_decision.get("recommendation"),
        )
        verification = self._post_output_verification(
            deterministic_recommendation,
            ai_decision,
            recommendation,
        )

        financing = {
            "financing_need_type": financing_type,
            "funding_gap": funding_gap,
            "financial_needs": finance.get("financial_needs")
            or finance_memory.get("financial_needs", []),
            **credit_match,
        }
        decision_card = {
            "recommendation": recommendation,
            "recommendation_reasons": self._decision_reasons(
                screening, finance, risk, partner_match, ai_decision
            ),
            "conditions": self._conditions(screening, finance, financing, partner_match),
            "mitigation_plan": self._mitigation_plan(screening, finance),
            "next_actions": self._next_actions(
                recommendation,
                financing_type,
                partner_match.get("matched_bank_product_id"),
            ),
            "agent_reasoning": {
                "ai_used": ai_decision.get("ai_used", False),
                "provider": ai_decision.get("provider"),
                "mode": ai_decision.get("mode"),
                "deterministic_recommendation": deterministic_recommendation,
                "ai_recommendation": ai_decision.get("recommendation"),
                "final_guarded_recommendation": recommendation,
                "summary": self._list(ai_decision.get("reasoning_summary"))[:5],
                "evidence_used": self._list(ai_decision.get("evidence_used"))[:6],
                "tradeoffs": self._list(ai_decision.get("tradeoffs"))[:4],
                "missing_info": self._list(ai_decision.get("missing_info"))[:4],
                "confidence": ai_decision.get("confidence", 0.0),
                "prompt_bytes": ai_decision.get("prompt_bytes"),
                "prevention_guardrails": [
                    "Decision Agent receives compact handoff only, not full database.",
                    "AI may recommend only Accept, Conditional Accept, or Reject.",
                    "Founder remains final approver.",
                    "Python blocks unsafe upgrades above deterministic guardrail.",
                ],
                "post_output_verification": verification,
                "guardrail_note": (
                    "Python guardrail keeps final recommendation at least as "
                    "conservative as deterministic business rules."
                ),
                "error": ai_decision.get("error"),
                "friendly_error": ai_decision.get("friendly_error"),
            },
            "human_in_the_loop": {
                "founder_shortlist_confirmation_required": screening[
                    "preliminary_screening_result"
                ]
                in {"Shortlist for Deep Assessment", "Conditional Shortlist", "Hold"},
                "founder_final_approval_required": True,
                "external_release_gate_required": financing_type != "None"
                and partner_match.get("matched_bank_product_id") is not None,
            },
        }
        ceo_decision = self._ceo_decision_output(
            recommendation,
            opportunity_profile,
            finance_memory,
            risk_memory,
            financing,
            partner_match,
            decision_card,
            ai_decision,
        )
        decision_card["ceo_readable"] = ceo_decision

        return {
            "agent_name": self.name,
            "role": self.role,
            "inputs": [
                "opportunity_knowledge_graph.agent_view: Decision & Partner Agent",
                "OpenAI-enriched Data & Finance screening/finance outputs",
                "Finance Memory",
                "Risk Memory",
                "10_CREDIT_PROFILE",
                "11_BANK_PRODUCTS",
            ],
            "actions": [
                "Resolve Decision & Partner graph view to identify credit, bank product, API, and HITL relationships.",
                "Read Finance Memory funding_gap/financial_needs and map them into financing_need_type.",
                "Reuse existing credit profile by contract_id before semantic matching.",
                "Filter bank products by financing keyword, requested amount, and customer segment.",
                "Ask the configured AI provider to read risk, financing, credit, and partner evidence before recommending.",
                "Validate AI recommendation with deterministic business guardrails.",
            ],
            "knowledge_graph_context": compact_graph_for(self.name),
            "sql_tool_plan": sql_plan_for_agent(
                self.name,
                contract_id=text(contract.get("contract_id")),
                requested_amount=credit_match.get("requested_amount"),
            ),
            "outputs": {
                "financing": financing,
                "partner": partner_match,
                "decision_card": decision_card,
                "ceo_decision": ceo_decision,
            },
            "handoff_to": "Founder Final Approval",
            "handoff_payload": {
                "recommendation": recommendation,
                "conditions": decision_card["conditions"],
                "external_release_gate_required": decision_card["human_in_the_loop"][
                    "external_release_gate_required"
                ],
                "decision_reasoning_summary": decision_card["agent_reasoning"][
                    "summary"
                ],
                "decision_evidence_used": decision_card["agent_reasoning"][
                    "evidence_used"
                ],
            },
        }

    def _financing_need_type(
        self,
        funding_need: str,
        payment_terms: Any,
        funding_gap: dict[str, Any] | None = None,
    ) -> str:
        primary_type = text((funding_gap or {}).get("primary_need_type"))
        if primary_type == "performance_bond":
            return "Performance Bond"
        if primary_type == "trade_finance":
            return "LC / Trade Finance"
        if primary_type == "working_capital":
            return "Working Capital"
        if primary_type == "none":
            return "None"
        if funding_need == "Not Needed":
            return "None"
        payment_terms = text(payment_terms)
        if payment_terms == "Performance bond required":
            return "Performance Bond"
        if payment_terms == "Possible LC/trade finance":
            return "LC / Trade Finance"
        if payment_terms in {"Monthly payment", "Milestone payment"}:
            return "Working Capital"
        return "Working Capital"

    def _primary_required_amount(self, assessment: dict[str, Any] | None) -> float | None:
        primary_type = text((assessment or {}).get("primary_need_type"))
        for need in (assessment or {}).get("needs", []) or []:
            if text(need.get("type")) == primary_type:
                return as_float(need.get("required_amount"), None)
        return None

    def _semantic_credit_match(self, request_type: str, financing_type: str) -> bool:
        request = request_type.lower()
        financing = financing_type.lower()
        if "performance bond" in financing:
            return "performance bond" in request
        if "trade" in financing or "lc" in financing:
            return "trade" in request or "lc" in request
        if "working capital" in financing:
            return "working capital" in request
        return False

    def _match_credit_case(
        self,
        credit_profiles: pd.DataFrame,
        contract_id: str,
        financing_type: str,
        total_open_ar: float,
        contract_value: float,
        gross_margin: float,
        assessed_required_amount: float | None = None,
    ) -> dict[str, Any]:
        if financing_type == "None":
            return {
                "matched_credit_case_id": None,
                "requested_amount": None,
                "eligibility_score": None,
                "credit_match_confidence": "Not Applicable",
                "multiple_match_ambiguous": False,
            }

        by_contract = credit_profiles[
            credit_profiles["collateral_or_basis"].astype(str).str.contains(
                contract_id, case=False, na=False
            )
        ]
        if not by_contract.empty:
            item = by_contract.iloc[0]
            return {
                "matched_credit_case_id": text(item.get("credit_case_id")),
                "requested_amount": as_float(item.get("requested_amount")),
                "eligibility_score": as_float(item.get("eligibility_score"), None),
                "credit_match_confidence": "High",
                "multiple_match_ambiguous": False,
                "precheck_note": text(item.get("precheck_note")),
            }

        semantic = credit_profiles[
            credit_profiles["request_type"].astype(str).apply(
                lambda value: self._semantic_credit_match(value, financing_type)
            )
        ]
        if not semantic.empty:
            ambiguous = len(semantic) >= 2
            if ambiguous:
                semantic = semantic.assign(
                    _distance=(
                        semantic["requested_amount"].astype(float) - total_open_ar
                    ).abs()
                ).sort_values("_distance")
            item = semantic.iloc[0]
            return {
                "matched_credit_case_id": text(item.get("credit_case_id")),
                "requested_amount": as_float(item.get("requested_amount")),
                "eligibility_score": as_float(item.get("eligibility_score"), None),
                "credit_match_confidence": "Low" if ambiguous else "Medium",
                "multiple_match_ambiguous": ambiguous,
                "precheck_note": text(item.get("precheck_note")),
            }

        requested_amount = assessed_required_amount
        if requested_amount is None:
            requested_amount = max(0.0, total_open_ar - contract_value * gross_margin)
        return {
            "matched_credit_case_id": None,
            "requested_amount": requested_amount,
            "eligibility_score": None,
            "credit_match_confidence": "No Evidence",
            "multiple_match_ambiguous": False,
            "precheck_note": "No existing credit profile matched; founder confirmation required.",
        }

    def _bank_keyword(self, financing_type: str) -> str | None:
        financing = financing_type.lower()
        if "performance bond" in financing:
            return "performance bond"
        if "trade" in financing or "lc" in financing:
            return "trade|lc"
        if "working capital" in financing:
            return "working capital"
        return None

    def _match_bank_products(
        self,
        bank_products: pd.DataFrame,
        financing_type: str,
        requested_amount: float | None,
        customer: dict[str, Any],
    ) -> dict[str, Any]:
        if financing_type == "None":
            return {
                "banking_fit_hint": "Not Applicable",
                "matched_bank_product_id": None,
                "confidence_score": None,
                "candidate_products": [],
            }

        keyword = self._bank_keyword(financing_type)
        if not keyword or requested_amount is None:
            return self._no_bank_match()

        if keyword == "trade|lc":
            product_match = bank_products["product_name"].astype(str).str.contains(
                r"trade|lc", case=False, regex=True, na=False
            )
        else:
            product_match = bank_products["product_name"].astype(str).str.contains(
                keyword, case=False, regex=False, na=False
            )
        amount_match = bank_products["minimum_amount"].astype(float) <= requested_amount
        candidates = bank_products[product_match & amount_match].copy()
        if candidates.empty:
            return self._no_bank_match()

        candidates["_segment_match"] = candidates["target_segment"].apply(
            lambda value: bool(segment_matches(value, customer))
        )
        exact = candidates[candidates["_segment_match"]]

        if len(exact) == 1:
            matched = exact.iloc[0]
            hint = f"{text(matched.get('bank'))} Fit"
            confidence = 0.90
        elif len(exact) >= 2:
            matched = exact.sort_values("annual_rate_or_fee").iloc[0]
            hint = "Multi-Partner"
            confidence = 0.75
        elif len(candidates) == 1:
            matched = candidates.iloc[0]
            hint = f"{text(matched.get('bank'))} Fit (Conditional)"
            confidence = 0.60
        else:
            matched = candidates.sort_values("annual_rate_or_fee").iloc[0]
            hint = f"{text(matched.get('bank'))} Fit (Conditional)"
            confidence = 0.60

        return {
            "banking_fit_hint": hint,
            "matched_bank_product_id": text(matched.get("bank_product_id")),
            "confidence_score": confidence,
            "candidate_products": records(candidates.drop(columns=["_segment_match"])),
        }

    def _no_bank_match(self) -> dict[str, Any]:
        return {
            "banking_fit_hint": "No Suitable Match",
            "matched_bank_product_id": None,
            "confidence_score": 0.20,
            "candidate_products": [],
        }

    def _recommendation(
        self, risk_level: str, banking_fit_hint: str, eligibility_score: Any
    ) -> str:
        if risk_level == "Low":
            return "Accept"

        fit_ok = (
            banking_fit_hint == "Not Applicable"
            or banking_fit_hint == "Multi-Partner"
            or banking_fit_hint.endswith(" Fit")
        )
        conditional_ok = "Fit (Conditional)" in banking_fit_hint
        no_match = banking_fit_hint == "No Suitable Match"
        eligibility = eligibility_score

        if risk_level == "Medium":
            return "Accept" if fit_ok else "Conditional Accept"

        if no_match:
            return "Reject"
        if eligibility is not None and (fit_ok or conditional_ok) and float(eligibility) >= 0.60:
            return "Conditional Accept"
        return "Reject"

    def _decision_reasons(
        self,
        screening: dict[str, Any],
        finance: dict[str, Any],
        risk: dict[str, Any],
        partner: dict[str, Any],
        ai_decision: dict[str, Any] | None = None,
    ) -> list[str]:
        reasons = []
        for flag in risk["applicable_risk_flags"]:
            action = text(flag.get("required_action"))
            if action:
                reasons.append(f"{flag['rule_id']}: {action}")
        if ai_decision:
            for item in self._list(ai_decision.get("reasoning_summary"))[:3]:
                reasons.append(f"AI decision reasoning: {text(item)}")
        if screening["data_readiness_status"] != "Ready":
            reasons.append(f"Data readiness: {screening['data_readiness_status']}")
        if screening.get("openai_risk_narrative"):
            reasons.append(f"OpenAI reasoning: {screening['openai_risk_narrative']}")
        if finance.get("openai_cashflow_reasoning"):
            reasons.append(f"OpenAI cashflow: {finance['openai_cashflow_reasoning']}")
        reasons.extend(screening["gateway_flags"])
        banking_hint = partner["banking_fit_hint"]
        if banking_hint and banking_hint != "Not Applicable":
            reasons.append(f"Banking fit: {banking_hint}")
        confidence = partner.get("confidence_score")
        if confidence is not None and confidence < 0.65:
            reasons.append("RR-006: độ tin cậy khớp đối tác ngân hàng thấp.")
        return reasons

    def _conditions(
        self,
        screening: dict[str, Any],
        finance: dict[str, Any],
        financing: dict[str, Any],
        partner: dict[str, Any],
    ) -> list[str]:
        conditions = []
        if screening["capacity_risk_flag"]:
            conditions.append("Phase rollout or add implementation partners before signing.")
        if screening["low_margin_flag"]:
            conditions.append("Review pricing/cost because gross margin is below service target.")
        if finance["cashflow_gap_flag"]:
            conditions.append("Confirm working-capital plan for months below cash reserve.")
        if financing["financing_need_type"] != "None":
            conditions.append(
                f"Use/review credit case {financing.get('matched_credit_case_id') or 'new case'} "
                f"for {financing['financing_need_type']}."
            )
        if partner["banking_fit_hint"] == "No Suitable Match":
            conditions.append("No bank product matched; founder must resolve partner path manually.")
        return conditions

    def _mitigation_plan(
        self, screening: dict[str, Any], finance: dict[str, Any]
    ) -> list[str]:
        plan = []
        if finance["cashflow_gap_flag"]:
            plan.append("Evaluate working capital line, invoice financing, or phase delivery.")
        if screening["capacity_risk_flag"]:
            plan.append("Split rollout by province cluster and secure contractor capacity.")
        if screening["low_margin_flag"]:
            plan.append("Reprice scope or reduce delivery cost before final approval.")
        if not plan:
            plan.append("Proceed with standard monitoring and founder approval.")
        return plan

    def _next_actions(
        self,
        recommendation: str,
        financing_need_type: str,
        matched_bank_product_id: str | None,
    ) -> list[str]:
        if recommendation == "Reject":
            return [
                "Lưu recommendation_reasons và lý do reject vào lịch sử.",
                "Không tạo payload gửi đối tác bên ngoài.",
            ]

        actions = ["Generate internal document packet for founder approval."]
        if financing_need_type != "None" and matched_bank_product_id:
            actions.append("Draft partner email/API payload with masked external fields.")
            actions.append("Trigger HITL External Release Gate before sending partner data.")
        elif financing_need_type == "None":
            actions.append("Create internal archive task only; no bank payload required.")
        else:
            actions.append("Create note: founder needs to contact partner manually.")
        return actions

    def _ceo_decision_output(
        self,
        recommendation: str,
        opportunity_profile: dict[str, Any],
        finance_memory: dict[str, Any],
        risk_memory: dict[str, Any],
        financing: dict[str, Any],
        partner_match: dict[str, Any],
        decision_card: dict[str, Any],
        ai_decision: dict[str, Any],
    ) -> dict[str, Any]:
        contract = finance_memory.get("contract") or opportunity_profile.get("contract", {})
        customer = finance_memory.get("customer") or opportunity_profile.get("customer", {})
        selected_product = self._selected_bank_product(partner_match, financing)
        confidence = (
            partner_match.get("confidence_score")
            if partner_match.get("confidence_score") is not None
            else ai_decision.get("confidence", 0.0)
        )
        return {
            "decision": self._ceo_decision_label(recommendation),
            "confidence_score": confidence,
            "approval_required": True,
            "contract_overview": {
                "contract_id": contract.get("contract_id"),
                "contract_value": contract.get("contract_value"),
                "gross_margin": contract.get("gross_margin"),
                "status": contract.get("status"),
                "payment_terms": contract.get("payment_terms"),
            },
            "customer_profile": {
                "customer_id": customer.get("customer_id"),
                "customer_type": customer.get("customer_type"),
                "payment_reliability": customer.get("payment_reliability"),
                "strategic_value": customer.get("strategic_value"),
                "industry": customer.get("industry"),
            },
            "order_summary": self._order_decision_summary(
                finance_memory.get("orders", []),
                selected_product,
                confidence,
            ),
            "bank_product_recommendation": selected_product,
            "reasons": decision_card.get("recommendation_reasons", []),
            "action_required": decision_card.get("conditions", []),
            "summary": self._ceo_summary(
                recommendation,
                risk_memory,
                selected_product,
                confidence,
            ),
        }

    def _ceo_decision_label(self, recommendation: str) -> str:
        return {
            "Accept": "GO",
            "Conditional Accept": "CONDITIONAL GO",
            "Reject": "NO GO",
        }.get(recommendation, "REVIEW")

    def _selected_bank_product(
        self,
        partner_match: dict[str, Any],
        financing: dict[str, Any],
    ) -> dict[str, Any]:
        candidates = partner_match.get("candidate_products") or []
        selected_id = partner_match.get("matched_bank_product_id")
        selected = {}
        for item in candidates:
            if text(item.get("bank_product_id")) == text(selected_id):
                selected = item
                break
        if not selected and candidates:
            selected = candidates[0]
        return {
            "product_id": selected_id,
            "bank": selected.get("bank") or self._bank_from_fit(
                partner_match.get("banking_fit_hint")
            ),
            "product_name": selected.get("product_name")
            or partner_match.get("banking_fit_hint"),
            "annual_rate": selected.get("annual_rate_or_fee"),
            "amount": financing.get("requested_amount"),
            "confidence_score": partner_match.get("confidence_score"),
            "fit_reason": partner_match.get("banking_fit_hint"),
        }

    def _order_decision_summary(
        self,
        orders: list[dict[str, Any]],
        selected_product: dict[str, Any],
        confidence: Any,
    ) -> list[dict[str, Any]]:
        rows = []
        for order_item in orders:
            need = text(order_item.get("financial_need")) or "None"
            amount = as_float(order_item.get("need_amount_estimate"), 0.0) or 0.0
            if need == "None":
                recommendation = "Không cần sản phẩm ngân hàng riêng cho order này"
                bank_product = "N/A"
            elif confidence is not None and float(confidence) < 0.65:
                recommendation = "Chờ bổ sung - confidence dưới ngưỡng 0.65"
                bank_product = selected_product.get("product_name") or "Pending"
            else:
                recommendation = f"Đề xuất - confidence {confidence}"
                bank_product = (
                    f"{selected_product.get('product_id')} - {selected_product.get('product_name')}"
                    if selected_product.get("product_id")
                    else selected_product.get("product_name") or "Pending"
                )
            rows.append(
                {
                    "order_id": order_item.get("order_id"),
                    "revenue": order_item.get("order_revenue"),
                    "margin": order_item.get("computed_margin"),
                    "status": order_item.get("status"),
                    "note": order_item.get("delivery_note"),
                    "financial_need": need,
                    "need_amount_estimate": amount,
                    "bank_product_recommended": bank_product,
                    "recommendation": recommendation,
                }
            )
        return rows

    def _ceo_summary(
        self,
        recommendation: str,
        risk_memory: dict[str, Any],
        selected_product: dict[str, Any],
        confidence: Any,
    ) -> str:
        return (
            f"Agent khuyến nghị {recommendation}. Risk level "
            f"{risk_memory.get('risk_level', 'N/A')}; sản phẩm phù hợp nhất là "
            f"{selected_product.get('product_name') or 'N/A'} với confidence {confidence}. "
            "Founder là người chốt cuối và cần xác nhận trước khi hồ sơ rời OPC."
        )

    def _bank_from_fit(self, fit_hint: Any) -> str | None:
        hint = text(fit_hint)
        if not hint or hint in {"No Suitable Match", "Not Applicable"}:
            return None
        return hint.replace(" Fit (Conditional)", "").replace(" Fit", "")

    def _run_ai_decision_reasoning(
        self,
        tables: dict[str, pd.DataFrame],
        opportunity_profile: dict[str, Any],
        screening: dict[str, Any],
        finance: dict[str, Any],
        finance_memory: dict[str, Any],
        risk: dict[str, Any],
        risk_memory: dict[str, Any],
        financing_type: str,
        credit_match: dict[str, Any],
        partner_match: dict[str, Any],
        deterministic_recommendation: str,
    ) -> dict[str, Any]:
        fallback = self._fallback_decision_reasoning(
            deterministic_recommendation,
            risk,
            financing_type,
            credit_match,
            partner_match,
        )
        contract = opportunity_profile.get("contract", {})
        payload = {
            "opportunity_profile": self._compact_opportunity_profile(
                opportunity_profile
            ),
            "screening_result": {
                "data_readiness_status": screening.get("data_readiness_status"),
                "preliminary_screening_result": screening.get(
                    "preliminary_screening_result"
                ),
                "feasibility_status": screening.get("feasibility_status"),
                "gateway_flags": screening.get("gateway_flags"),
            },
            "finance_signal": {
                "funding_need": finance.get("funding_need"),
                "financing_need_type": financing_type,
                "funding_gap": finance.get("funding_gap"),
                "financial_needs": finance.get("financial_needs"),
                "required_prechecks": finance.get("required_prechecks"),
                "cashflow_gap_flag": finance.get("cashflow_gap_flag"),
                "cashflow_gap_months": finance.get("cashflow_gap_months"),
                "total_open_ar": finance.get("total_open_ar"),
                "bank_service_required_flag": finance.get(
                    "bank_service_required_flag"
                ),
            },
            "finance_memory": finance_memory,
            "risk_signal": self._compact_risk(risk),
            "risk_memory": risk_memory,
            "credit_match": self._compact_match(credit_match),
            "partner_match": self._compact_match(partner_match),
            "knowledge_graph_rule_catalog": compact_rules_for(
                "Decision & Partner Agent"
            ),
            "opportunity_knowledge_graph": compact_graph_for(
                "Decision & Partner Agent"
            ),
            "sql_tool_plan": sql_plan_for_agent(
                "Decision & Partner Agent",
                contract_id=contract.get("contract_id"),
                requested_amount=credit_match.get("requested_amount"),
            ),
            "agent_guardrails": [
                "Use only supplied evidence.",
                "Do not invent products, rule IDs, amounts, or approvals.",
                "Founder is final approver; recommendation is advisory.",
                "AI may be more conservative than deterministic guardrail, not less.",
            ],
            "deterministic_guardrail_recommendation": deterministic_recommendation,
            "recommendation_options": ["Accept", "Conditional Accept", "Reject"],
        }
        system_prompt = (
            "You are OPC's Decision Agent, the final reasoning agent before the "
            "Founder sees the decision card. You consume Shared Memory from the "
            "Finance Agent and Risk Agent; do not re-invent database facts. Your "
            "job is to map financial_needs and funding_gap into bank-product "
            "options, evaluate eligibility/confidence, respect precheck and human "
            "approval rules, and produce an advisory recommendation only. Domain "
            "logic: performance bond, working capital, and trade finance are "
            "different financing needs; missing documents should trigger request "
            "for more information; confidence below 0.65 should not be pushed to "
            "external partner; Founder remains final approver. Prevention guardrail: "
            "use only supplied Finance Memory, Risk Memory, product/credit evidence, "
            "knowledge graph context and rule catalog. Verification guardrail: after "
            "drafting output, verify the recommendation is consistent with risk_level, "
            "confidence_score, approval_required and evidence_used. Return concise "
            "auditable reasoning only, not private chain-of-thought."
        )
        task_prompt = (
            "Return JSON only with keys: recommendation (Accept/Conditional Accept/Reject), "
            "reasoning_summary (array of 3-5 Vietnamese bullets), "
            "evidence_used (array of field=value strings), tradeoffs (array), "
            "missing_info (array), confidence (number 0-1). INPUT_JSON:\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )
        return AgenticAIClient(
            provider_env="DECISION_AI_PROVIDER",
            api_key_env="DECISION_GROQ_API_KEY",
            model_env="DECISION_GROQ_MODEL",
        ).complete_json(system_prompt, task_prompt, fallback)

    def _compact_opportunity_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        contract = profile.get("contract", {})
        customer = profile.get("customer", {})
        return {
            "contract_id": contract.get("contract_id"),
            "customer_id": contract.get("customer_id") or customer.get("customer_id"),
            "customer_name": customer.get("customer_name"),
            "customer_type": customer.get("customer_type"),
            "industry": customer.get("industry"),
            "strategic_value": customer.get("strategic_value"),
            "payment_reliability": customer.get("payment_reliability"),
            "banking_fit_hint": customer.get("banking_fit_hint"),
            "contract_value": contract.get("contract_value"),
            "gross_margin": contract.get("gross_margin"),
            "payment_terms": contract.get("payment_terms"),
            "description": contract.get("description"),
            "order_count": len(profile.get("orders", []) or []),
        }

    def _compact_screening(self, screening: dict[str, Any]) -> dict[str, Any]:
        keys = [
            "data_readiness_status",
            "preliminary_screening_result",
            "feasibility_status",
            "gateway_flags",
            "low_margin_flag",
            "margin_gap_severity",
            "customer_payment_risk",
            "delivery_delay_risk_flag",
            "capacity_risk_flag",
            "province_count",
            "openai_confidence",
        ]
        return {key: screening.get(key) for key in keys}

    def _compact_finance(self, finance: dict[str, Any]) -> dict[str, Any]:
        keys = [
            "funding_need",
            "financing_need_type",
            "funding_gap",
            "financial_needs",
            "required_prechecks",
            "cashflow_gap_flag",
            "cashflow_gap_months",
            "total_open_ar",
            "total_estimated_cost",
            "bank_service_required_flag",
            "openai_cashflow_reasoning",
            "openai_bank_service_required_flag",
        ]
        return {key: finance.get(key) for key in keys}

    def _compact_risk(self, risk: dict[str, Any]) -> dict[str, Any]:
        return {
            "risk_level": risk.get("risk_level"),
            "applicable_risk_flags": [
                {
                    "rule_id": flag.get("rule_id"),
                    "severity": flag.get("severity"),
                    "required_action": flag.get("required_action"),
                    "owner_agent": flag.get("owner_agent"),
                }
                for flag in risk.get("applicable_risk_flags", [])
            ],
            "agent_reasoning": {
                "summary": risk.get("agent_reasoning", {}).get("summary"),
                "evidence_used": risk.get("agent_reasoning", {}).get(
                    "evidence_used"
                ),
                "final_rule_ids": risk.get("agent_reasoning", {}).get(
                    "final_rule_ids"
                ),
            },
        }

    def _compact_match(self, match: dict[str, Any]) -> dict[str, Any]:
        keys = [
            "matched_credit_case_id",
            "matched_bank_product_id",
            "banking_fit_hint",
            "eligibility_score",
            "confidence_score",
            "selected_api_id",
            "partner_release_required",
        ]
        return {key: match.get(key) for key in keys if key in match}

    def _compact_catalog(
        self, rows: list[dict[str, Any]], keys: list[str]
    ) -> list[dict[str, Any]]:
        return [
            {key: item.get(key) for key in keys if key in item}
            for item in rows[:8]
        ]

    def _guarded_recommendation(self, deterministic: str, ai_value: Any) -> str:
        valid = {"Accept", "Conditional Accept", "Reject"}
        ai_recommendation = text(ai_value)
        if ai_recommendation not in valid:
            return deterministic
        risk_rank = {"Accept": 0, "Conditional Accept": 1, "Reject": 2}
        return (
            ai_recommendation
            if risk_rank[ai_recommendation] > risk_rank[deterministic]
            else deterministic
        )

    def _post_output_verification(
        self,
        deterministic: str,
        ai_decision: dict[str, Any],
        final_recommendation: str,
    ) -> dict[str, Any]:
        valid = {"Accept", "Conditional Accept", "Reject"}
        ai_value = text(ai_decision.get("recommendation"))
        risk_rank = {"Accept": 0, "Conditional Accept": 1, "Reject": 2}
        checks = [
            {
                "name": "ai_recommendation_is_allowed_value",
                "passed": ai_value in valid,
                "details": f"ai_recommendation={ai_value or 'missing'}",
            },
            {
                "name": "ai_output_not_less_conservative_than_guardrail",
                "passed": ai_value not in valid
                or risk_rank[final_recommendation] >= risk_rank[deterministic],
                "details": (
                    f"deterministic={deterministic}; final={final_recommendation}"
                ),
            },
            {
                "name": "decision_evidence_present",
                "passed": bool(self._list(ai_decision.get("evidence_used")))
                or ai_decision.get("mode") == "fallback",
                "details": "evidence_used checked after AI output.",
            },
            {
                "name": "confidence_range_valid",
                "passed": 0 <= float(ai_decision.get("confidence", 0) or 0) <= 1,
                "details": f"confidence={ai_decision.get('confidence', 0)}",
            },
        ]
        corrective_actions = []
        if ai_value not in valid:
            corrective_actions.append(
                "Ignored invalid AI recommendation and kept deterministic recommendation."
            )
        elif final_recommendation != ai_value:
            corrective_actions.append(
                "Adjusted final recommendation with Python guardrail after AI output."
            )
        return {
            "stage": "after_ai_output",
            "passed": all(item["passed"] for item in checks),
            "checks": checks,
            "corrective_actions": corrective_actions
            or ["AI decision output accepted after guardrail verification."],
        }

    def _fallback_decision_reasoning(
        self,
        recommendation: str,
        risk: dict[str, Any],
        financing_type: str,
        credit_match: dict[str, Any],
        partner_match: dict[str, Any],
    ) -> dict[str, Any]:
        rule_ids = [flag["rule_id"] for flag in risk.get("applicable_risk_flags", [])]
        return {
            "recommendation": recommendation,
            "reasoning_summary": [
                f"Fallback guardrail recommendation = {recommendation}.",
                f"Risk level = {risk.get('risk_level')} from rules {', '.join(rule_ids) or 'none'}.",
                f"Financing type = {financing_type}; banking fit = {partner_match.get('banking_fit_hint')}.",
            ],
            "evidence_used": [
                f"risk_level={risk.get('risk_level')}",
                f"applicable_risk_flags={', '.join(rule_ids) or 'none'}",
                f"financing_type={financing_type}",
                f"eligibility_score={credit_match.get('eligibility_score')}",
                f"banking_fit_hint={partner_match.get('banking_fit_hint')}",
            ],
            "tradeoffs": [
                "Fallback mode keeps deterministic decision rules as guardrail."
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
