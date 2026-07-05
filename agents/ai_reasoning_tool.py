from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from dotenv import load_dotenv

from agents.knowledge_base import compact_guardrails_for, compact_rules_for
from agents.knowledge_graph import compact_graph_for, sql_plan_for_agent
from agents.shared import as_float, text


class AIReasoningTool:
    name = "AI/NLP Reasoning Tool"
    role = (
        "Internal AI/NLP tool used by Data & Finance Agent for core business "
        "reasoning over unstructured contract text, delivery notes, and preliminary "
        "finance signals before Risk & Decision run."
    )

    def run(self, data_finance_output: dict[str, Any]) -> dict[str, Any]:
        payload = self._build_payload(data_finance_output)
        result: dict[str, Any]
        error = None
        provider = self._provider()
        mode = provider

        try:
            result = self._call_ai(payload, provider)
            result["ai_used"] = True
            result["openai_used"] = provider == "openai"
            result["provider"] = provider
            result["mode"] = provider
        except Exception as exc:
            error = str(exc)
            mode = "fallback"
            result = self._fallback_reasoning(payload)
            result["ai_used"] = False
            result["openai_used"] = False
            result["provider"] = provider
            result["mode"] = "fallback"
            result["error"] = error

        result["prevention_guardrails"] = [
            "Use only supplied contract/payment/order/finance evidence.",
            "Return structured JSON only.",
            "List uncertainty or data gaps instead of guessing.",
            "Downstream Python guardrails remain authoritative.",
        ]
        result = self._verify_output_against_input(result, payload)

        return {
            "agent_name": self.name,
            "role": self.role,
            "inputs": [
                "Data & Finance Agent opportunity_profile",
                "Data & Finance Agent screening/finance outputs",
                "OPENAI_API_KEY, GEMINI_API_KEY, or GROQ_API_KEY",
            ],
            "actions": [
                "Read Data & Finance Agent slice from opportunity_knowledge_graph before prompting the provider.",
                "Ask the configured AI provider to extract rollout scale, banking requirement, and operational complexity from unstructured contract/delivery text.",
                "Ask the configured AI provider to explain cashflow and risk implications in structured JSON.",
                "Feed the structured reasoning back into screening/finance before Risk & Compliance Agent runs.",
            ],
            "knowledge_graph_context": compact_graph_for("Data & Finance Agent"),
            "sql_tool_plan": sql_plan_for_agent(
                "Data & Finance Agent",
                contract_id=payload.get("contract_id"),
            ),
            "outputs": {
                "openai_reasoning": result,
                "core_decision_effect": self._core_decision_effect(result),
            },
            "handoff_to": "Risk & Compliance Agent",
            "handoff_payload": {
                "mode": mode,
                "provider": provider,
                "ai_used": result.get("ai_used", False),
                "openai_used": result.get("openai_used", False),
                "province_count": result.get("province_count"),
                "bank_service_required_flag": result.get("bank_service_required_flag"),
                "operational_complexity": result.get("operational_complexity"),
                "recommended_focus": result.get("recommended_focus"),
                "logic_summary": result.get("logic_summary"),
                "evidence_used": result.get("evidence_used"),
                "confidence": result.get("confidence"),
                "error": error,
                "post_output_verification": result.get("post_output_verification"),
            },
        }

    def _verify_output_against_input(
        self, result: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        text_blob = " ".join(
            [
                text(payload.get("contract_description")),
                text(payload.get("payment_terms")),
                *[text(item) for item in payload.get("delivery_notes", [])],
            ]
        ).lower()
        finance = payload.get("preliminary_finance", {})
        bank_keywords = ("lc", "trade finance", "bond", "letter of credit")
        bank_signal_supported = any(keyword in text_blob for keyword in bank_keywords)
        ai_bank_signal = bool(result.get("bank_service_required_flag"))

        checks = [
            {
                "name": "required_json_fields_present",
                "passed": all(
                    key in result
                    for key in [
                        "cashflow_reasoning",
                        "risk_narrative",
                        "bank_service_required_flag",
                        "confidence",
                    ]
                ),
            },
            {
                "name": "bank_service_signal_supported_by_text_or_rule",
                "passed": (not ai_bank_signal)
                or bank_signal_supported
                or bool(finance.get("bank_service_required_flag_rule")),
            },
            {
                "name": "cashflow_reasoning_supported_by_finance_signal",
                "passed": bool(finance.get("cashflow_gap_flag"))
                or bool(finance.get("total_open_ar"))
                or "cashflow" not in text(result.get("cashflow_reasoning")).lower(),
            },
            {
                "name": "confidence_range_valid",
                "passed": 0 <= float(result.get("confidence", 0) or 0) <= 1,
            },
        ]

        corrective_actions = []
        if not checks[1]["passed"]:
            result["bank_service_required_flag"] = bool(
                finance.get("bank_service_required_flag_rule")
            )
            corrective_actions.append(
                "bank_service_required_flag reset to source rule because AI signal lacked text/rule evidence."
            )

        result["post_output_verification"] = {
            "stage": "after_ai_output",
            "passed": all(item["passed"] for item in checks),
            "checks": checks,
            "corrective_actions": corrective_actions
            or ["AI output accepted after evidence verification."],
        }
        return result

    def _provider(self) -> str:
        load_dotenv(override=True)
        provider = os.getenv("AI_PROVIDER", "groq").strip().lower()
        return provider if provider in {"openai", "gemini", "groq"} else "groq"

    def _call_ai(self, payload: dict[str, Any], provider: str) -> dict[str, Any]:
        if provider == "gemini":
            return self._call_gemini(payload)
        if provider == "groq":
            return self._call_groq(payload)
        return self._call_openai(payload)

    def _prompt(self, payload: dict[str, Any]) -> str:
        return (
            "SYSTEM ROLE: You are an AI/NLP reasoning tool inside the OPC Data & Finance Agent. "
            "opportunity workflow. You are not a report writer. Your job is to read "
            "the collected opportunity data, identify business meaning that simple "
            "rules may miss, and return structured signals that downstream Risk and "
            "Decision agents will consume.\n\n"
            "BUSINESS OBJECTIVE: Help OPC decide whether a contract opportunity can "
            "move forward, what implementation/cashflow risks exist, and whether "
            "banking support such as working capital, LC/trade finance, or performance "
            "bond is needed.\n\n"
            "DATA TO READ: contract description, payment terms, contract value, gross "
            "margin, customer segment, delivery notes, order statuses, preliminary "
            "screening flags, AR exposure, estimated cost, cashflow gap months, and "
            "bank-service rule signals.\n\n"
            "REASONING PROTOCOL:\n"
            "1. Extract factual signals from text and numbers, especially rollout scale, "
            "province count, payment/banking terms, delivery complexity, and cashflow pressure.\n"
            "2. Compare extracted signals with preliminary rule outputs. If they conflict, "
            "state the conflict and choose the safer interpretation.\n"
            "3. Infer operational complexity from rollout scale, delivery notes, order status, "
            "and implementation capacity risk.\n"
            "4. Infer cashflow pressure from AR, estimated cost, cashflow gap months, and "
            "payment/banking terms.\n"
            "5. Produce concise Vietnamese rationale summaries. Do not reveal private chain-of-thought; "
            "return short, auditable reasoning bullets and evidence only.\n\n"
            "Return only valid JSON with exactly these keys: "
            "province_count (integer or null), "
            "bank_service_required_flag (boolean), "
            "operational_complexity (Low/Medium/High), "
            "cashflow_reasoning (short Vietnamese sentence), "
            "risk_narrative (short Vietnamese sentence), "
            "logic_summary (array of 3-5 concise Vietnamese reasoning bullets), "
            "evidence_used (array of 3-6 short evidence strings naming fields/values used), "
            "assumptions_or_gaps (array of 0-4 short Vietnamese strings), "
            "recommended_focus (array of 2-4 short Vietnamese strings), "
            "confidence (number 0-1). "
            "Your output directly changes downstream risk and decision logic, "
            "so be conservative, evidence-based, cite rule/evidence, and explicit "
            "about uncertainty. Follow agent_guardrails: do not invent data, cite "
            "field=value evidence, list missing_info instead of guessing, and do "
            "not reveal private chain-of-thought."
            f"\n\nINPUT_JSON:\n{json.dumps(payload, ensure_ascii=False)}"
        )

    def _call_openai(self, payload: dict[str, Any]) -> dict[str, Any]:
        load_dotenv(override=True)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is missing.")

        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        base_url = os.getenv("OPENAI_BASE_URL") or None
        verify_ssl = os.getenv("OPENAI_SSL_VERIFY", "true").strip().lower() not in {
            "0",
            "false",
            "no",
        }
        http_client = None if verify_ssl else httpx.Client(verify=False, timeout=8)
        llm = ChatOpenAI(
            model=model,
            temperature=0,
            api_key=api_key,
            timeout=8,
            max_retries=0,
            http_client=http_client,
            base_url=base_url,
        )
        response = llm.invoke(
            [
                SystemMessage(
                    content=(
                        "You are an OPC business opportunity reasoning agent. "
                        "Read collected data, infer business risk logically, and produce auditable structured reasoning. "
                        "Return only valid JSON. Do not write markdown. "
                        "Your output directly changes downstream risk and decision logic, "
                        "so be conservative and evidence-based."
                    )
                ),
                HumanMessage(
                    content=self._prompt(payload)
                ),
            ]
        )
        return self._normalize_result(self._parse_json(response.content))

    def _call_gemini(self, payload: dict[str, Any]) -> dict[str, Any]:
        load_dotenv(override=True)
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is missing.")

        model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        verify_ssl = os.getenv("GEMINI_SSL_VERIFY", "false").strip().lower() not in {
            "0",
            "false",
            "no",
        }
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        body = {
            "contents": [{"parts": [{"text": self._prompt(payload)}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
        with httpx.Client(verify=verify_ssl, timeout=12) as client:
            response = client.post(url, params={"key": api_key}, json=body)
            response.raise_for_status()
            data = response.json()
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        return self._normalize_result(self._parse_json(content))

    def _call_groq(self, payload: dict[str, Any]) -> dict[str, Any]:
        load_dotenv(override=True)
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is missing.")

        model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        base_url = self._groq_base_url(
            os.getenv("GROQ_BASE_URL", "https://api.groq.com")
        )
        verify_ssl = os.getenv("GROQ_SSL_VERIFY", "false").strip().lower() not in {
            "0",
            "false",
            "no",
        }
        body = {
            "model": model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an OPC business opportunity reasoning agent. "
                        "Read collected data, infer business risk logically, and produce auditable structured reasoning. "
                        "Return only valid JSON. Do not write markdown. "
                        "Your output directly changes downstream risk and decision logic."
                    ),
                },
                {"role": "user", "content": self._prompt(payload)},
            ],
        }
        with httpx.Client(verify=verify_ssl, timeout=20) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        return self._normalize_result(self._parse_json(content))

    def _groq_base_url(self, value: str) -> str:
        base_url = (value or "https://api.groq.com").rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url.removesuffix("/chat/completions")
        if base_url.endswith("/openai/v1") or base_url.endswith("/v1"):
            return base_url
        return f"{base_url}/openai/v1"

    def _build_payload(self, data_finance_output: dict[str, Any]) -> dict[str, Any]:
        profile = data_finance_output["outputs"]["opportunity_profile"]
        screening = data_finance_output["outputs"]["screening"]
        finance = data_finance_output["outputs"]["finance"]
        contract = profile["contract"]
        orders = profile["orders"]
        return {
            "contract_id": contract.get("contract_id"),
            "customer_name": profile["customer"].get("customer_name"),
            "customer_type": profile["customer"].get("customer_type"),
            "contract_description": contract.get("description"),
            "payment_terms": contract.get("payment_terms"),
            "contract_value": contract.get("contract_value"),
            "gross_margin": contract.get("gross_margin"),
            "delivery_notes": [item.get("delivery_note") for item in orders][:5],
            "order_statuses": [item.get("status") for item in orders][:5],
            "preliminary_screening": {
                "data_readiness_status": screening.get("data_readiness_status"),
                "feasibility_status": screening.get("feasibility_status"),
                "province_count_rule": screening.get("province_count"),
                "capacity_risk_flag_rule": screening.get("capacity_risk_flag"),
                "gateway_flags": screening.get("gateway_flags"),
            },
            "preliminary_finance": {
                "total_open_ar": finance.get("total_open_ar"),
                "total_estimated_cost": finance.get("total_estimated_cost"),
                "cashflow_gap_flag": finance.get("cashflow_gap_flag"),
                "cashflow_gap_months": finance.get("cashflow_gap_months"),
                "bank_service_required_flag_rule": finance.get(
                    "bank_service_required_flag"
                ),
                "funding_need": finance.get("funding_need"),
                "funding_gap": finance.get("funding_gap"),
                "financial_needs": finance.get("financial_needs"),
                "required_prechecks": finance.get("required_prechecks"),
            },
            "knowledge_graph_rule_catalog": compact_rules_for("Data & Finance Agent"),
            "opportunity_knowledge_graph": compact_graph_for("Data & Finance Agent"),
            "sql_tool_plan": sql_plan_for_agent(
                "Data & Finance Agent",
                contract_id=contract.get("contract_id"),
            ),
            "agent_guardrails": compact_guardrails_for("Data & Finance Agent"),
        }

    def _parse_json(self, content: Any) -> dict[str, Any]:
        raw = text(content)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    def _normalize_result(self, result: dict[str, Any]) -> dict[str, Any]:
        province_count = result.get("province_count")
        if province_count in {"", "null"}:
            province_count = None
        elif province_count is not None:
            province_count = int(float(province_count))

        confidence = as_float(result.get("confidence"), 0.0) or 0.0
        complexity = text(result.get("operational_complexity")) or "Medium"
        if complexity not in {"Low", "Medium", "High"}:
            complexity = "Medium"

        focus = result.get("recommended_focus") or []
        if isinstance(focus, str):
            focus = [focus]
        logic_summary = result.get("logic_summary") or []
        if isinstance(logic_summary, str):
            logic_summary = [logic_summary]
        evidence_used = result.get("evidence_used") or []
        if isinstance(evidence_used, str):
            evidence_used = [evidence_used]
        assumptions_or_gaps = result.get("assumptions_or_gaps") or []
        if isinstance(assumptions_or_gaps, str):
            assumptions_or_gaps = [assumptions_or_gaps]

        return {
            "province_count": province_count,
            "bank_service_required_flag": bool(
                result.get("bank_service_required_flag")
            ),
            "operational_complexity": complexity,
            "cashflow_reasoning": text(result.get("cashflow_reasoning")),
            "risk_narrative": text(result.get("risk_narrative")),
            "logic_summary": [
                text(item) for item in logic_summary if text(item)
            ][:5],
            "evidence_used": [
                text(item) for item in evidence_used if text(item)
            ][:6],
            "assumptions_or_gaps": [
                text(item) for item in assumptions_or_gaps if text(item)
            ][:4],
            "recommended_focus": [text(item) for item in focus if text(item)][:4],
            "confidence": max(0.0, min(1.0, confidence)),
        }

    def _fallback_reasoning(self, payload: dict[str, Any]) -> dict[str, Any]:
        searchable_text = " ".join(
            [
                text(payload.get("contract_description")),
                text(payload.get("payment_terms")),
                *[text(item) for item in payload.get("delivery_notes", [])],
            ]
        )
        province_count = self._extract_province_count(searchable_text)
        bank_required = bool(
            re.search(
                r"\b(LC|trade finance|bond|letter of credit|performance bond)\b",
                searchable_text,
                re.IGNORECASE,
            )
        )
        finance = payload.get("preliminary_finance", {})
        cashflow_gap = bool(finance.get("cashflow_gap_flag"))
        open_ar = as_float(finance.get("total_open_ar"), 0.0) or 0.0
        estimated_cost = as_float(finance.get("total_estimated_cost"), 0.0) or 0.0

        if province_count is not None and province_count >= 10:
            complexity = "High"
        elif cashflow_gap or bank_required:
            complexity = "Medium"
        else:
            complexity = "Low"

        return {
            "province_count": province_count,
            "bank_service_required_flag": bank_required,
            "operational_complexity": complexity,
            "cashflow_reasoning": (
                "Fallback rule: cần tài trợ vì có cashflow gap hoặc AR/cost tạo áp lực."
                if cashflow_gap or open_ar >= estimated_cost
                else "Fallback rule: chưa thấy áp lực dòng tiền lớn."
            ),
            "risk_narrative": (
                "Fallback rule: rollout nhiều tỉnh hoặc điều khoản ngân hàng làm tăng rủi ro triển khai."
                if complexity != "Low"
                else "Fallback rule: rủi ro vận hành thấp theo dữ liệu hiện có."
            ),
            "logic_summary": [
                f"Mô tả hợp đồng cho thấy rollout khoảng {province_count or 'không rõ'} tỉnh.",
                "Điều khoản thanh toán/delivery note có tín hiệu cần dịch vụ ngân hàng."
                if bank_required
                else "Chưa thấy tín hiệu ngân hàng rõ trong payment terms/delivery notes.",
                "Cashflow gap hoặc AR so với estimated cost tạo áp lực vốn lưu động."
                if cashflow_gap or open_ar >= estimated_cost
                else "AR/cost chưa tạo áp lực vốn lưu động lớn theo rule fallback.",
            ],
            "evidence_used": [
                f"contract_description={text(payload.get('contract_description'))}",
                f"payment_terms={text(payload.get('payment_terms'))}",
                f"total_open_ar={open_ar}",
                f"total_estimated_cost={estimated_cost}",
                f"cashflow_gap_flag={cashflow_gap}",
            ],
            "assumptions_or_gaps": [
                "Fallback mode: AI provider không trả kết quả, dùng rule deterministic.",
            ],
            "recommended_focus": [
                "Kiểm tra rollout scale",
                "Xác nhận nhu cầu ngân hàng",
                "Đưa qua HITL trước khi ra quyết định",
            ],
            "confidence": 0.45,
        }

    def _extract_province_count(self, raw: str) -> int | None:
        match = re.search(r"(\d+)\s*[- ]?\s*province", raw, re.IGNORECASE)
        if match:
            return int(match.group(1))
        match = re.search(r"(\d+)\s*(tỉnh|tinh)", raw, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    def _core_decision_effect(self, result: dict[str, Any]) -> list[str]:
        effects = []
        if result.get("province_count") is not None:
            effects.append("province_count updates screening capacity assessment")
        if result.get("bank_service_required_flag"):
            effects.append("bank_service_required_flag updates finance funding_need")
        if result.get("operational_complexity") == "High":
            effects.append("High complexity forces conditional feasibility")
        if not effects:
            effects.append("Reasoning is recorded for HITL review without forcing a rule")
        return effects
