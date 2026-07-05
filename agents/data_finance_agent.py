from __future__ import annotations
import re
from datetime import date
from typing import Any
import pandas as pd
from agents.knowledge_graph import compact_graph_for, sql_plan_for_agent
from agents.shared import (
    TARGET_CUSTOMER_SEGMENTS,
    as_date,
    as_float,
    clean,
    json_value,
    month_key,
    profile_value,
    records,
    row,
    segment_matches,
    text,
)


BANK_SIGNAL_PATTERN = re.compile(
    r"\b(LC|trade finance|bond|letter of credit|performance bond)\b",
    re.IGNORECASE,
)
MATERIAL_CASHFLOW_COST_THRESHOLD = 300_000_000
PERFORMANCE_BOND_ESTIMATE_RATE = 0.10


class DataFinanceAgent:
    name = "Data & Finance Agent"
    role = (
        "Create Opportunity Profile, screen customer/contract readiness, "
        "check implementation feasibility, AR exposure, cashflow gap, and funding need."
    )

    def run(
        self,
        tables: dict[str, pd.DataFrame],
        contract_id: str,
        evaluation_date: date,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        context = self._build_context(tables, contract_id, evaluation_date)
        contract = context["contract"]
        opportunity_profile = self._opportunity_profile(context)
        screening = self._screening(context)
        finance = self._finance(context)

        output = {
            "agent_name": self.name,
            "role": self.role,
            "inputs": [
                "opportunity_knowledge_graph.agent_view: Data & Finance Agent",
                "04_CONTRACTS",
                "03_CUSTOMERS",
                "05_PRODUCTS",
                "06_ORDERS",
                "07_INVOICES",
                "08_BANK_TXN",
                "09_CASHFLOW",
                "14_ALERTS",
            ],
            "actions": [
                "Resolve knowledge graph view to identify allowed entities, rules, and SQL tools.",
                "Filter opportunity contracts by Negotiation/Pending expansion.",
                "Join customer, orders, services, invoices, cashflow, and alerts.",
                "Compute data readiness, customer payment risk, contract screening, feasibility, AR, cashflow, bank-service signal, and funding need.",
            ],
            "knowledge_graph_context": compact_graph_for(self.name),
            "sql_tool_plan": sql_plan_for_agent(
                self.name,
                contract_id=text(contract.get("contract_id")),
                customer_id=text(contract.get("customer_id")),
            ),
            "outputs": {
                "opportunity_profile": opportunity_profile,
                "screening": screening,
                "finance": finance,
            },
            "handoff_to": "Risk & Compliance Agent",
            "handoff_payload": {
                "low_margin_flag": screening["low_margin_flag"],
                "cashflow_gap_flag": finance["cashflow_gap_flag"],
                "delivery_delay_risk_flag": screening["delivery_delay_risk_flag"],
                "funding_need": finance["funding_need"],
                "funding_gap": finance["funding_gap"],
                "financial_needs": finance["financial_needs"],
            },
        }
        output["outputs"]["finance_memory"] = self._finance_memory(
            context, screening, finance
        )
        context.update(output["outputs"])
        return output, context

    def run_intake_screening(
        self,
        tables: dict[str, pd.DataFrame],
        contract_id: str,
        evaluation_date: date,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        context = self._build_context(tables, contract_id, evaluation_date)
        contract = context["contract"]
        opportunity_profile = self._opportunity_profile(context)
        screening = self._screening(context)

        output = {
            "agent_name": "Data Intake & Screening Agent",
            "role": (
                "Run business workflow steps 1-2: create Opportunity Profile, "
                "check data readiness, customer/contract screening, gateway flags, "
                "and feasibility before founder shortlist confirmation."
            ),
            "inputs": [
                "opportunity_knowledge_graph.agent_view: Data & Finance Agent",
                "04_CONTRACTS",
                "03_CUSTOMERS",
                "05_PRODUCTS",
                "06_ORDERS",
                "07_INVOICES",
                "08_BANK_TXN",
                "14_ALERTS",
            ],
            "actions": [
                "Resolve knowledge graph view to identify allowed entities, rules, and SQL tools.",
                "Filter opportunity contract and build traceable Opportunity Profile.",
                "Evaluate customer payment risk, segment fit, contract margin/payment pressure, and service fit.",
                "Run feasibility, delivery-delay exposure, and gateway routing before deep finance analysis.",
            ],
            "knowledge_graph_context": compact_graph_for("Data & Finance Agent"),
            "sql_tool_plan": sql_plan_for_agent(
                "Data & Finance Agent",
                contract_id=text(contract.get("contract_id")),
                customer_id=text(contract.get("customer_id")),
            ),
            "outputs": {
                "opportunity_profile": opportunity_profile,
                "screening": screening,
            },
            "handoff_to": "Founder Shortlist Confirmation",
            "handoff_payload": {
                "data_readiness_status": screening["data_readiness_status"],
                "preliminary_screening_result": screening[
                    "preliminary_screening_result"
                ],
                "gateway_flags": screening["gateway_flags"],
                "low_margin_flag": screening["low_margin_flag"],
                "delivery_delay_risk_flag": screening["delivery_delay_risk_flag"],
                "capacity_risk_flag": screening["capacity_risk_flag"],
            },
        }
        context.update(output["outputs"])
        return output, context

    def run_finance_after_shortlist(
        self,
        tables: dict[str, pd.DataFrame],
        data_finance_output: dict[str, Any],
        evaluation_date: date,
    ) -> dict[str, Any]:
        contract_id = data_finance_output["outputs"]["opportunity_profile"][
            "linked_keys"
        ]["contract_id"]
        context = self._build_context(tables, contract_id, evaluation_date)
        finance = self._finance(context)
        screening = data_finance_output["outputs"]["screening"]

        data_finance_output["agent_name"] = "Data & Finance Agent"
        data_finance_output["role"] = (
            "Continue business workflow step 3 after founder shortlist approval: "
            "calculate AR exposure, cash reserve gap, NLP bank-service signals, "
            "funding need, and AI/NLP reasoning before Risk & Compliance runs."
        )
        data_finance_output["inputs"] = [
            *data_finance_output["inputs"],
            "09_CASHFLOW",
            "Founder shortlist confirmation",
        ]
        data_finance_output["actions"] = [
            *data_finance_output["actions"],
            "After founder shortlist approval, compute total_open_ar and total_estimated_cost.",
            "Compare deployment months against 09_CASHFLOW projected_closing_cash and cash_reserve_minimum.",
            "Scan payment_terms and delivery_note for LC, trade finance, or bond signals before AI validation.",
        ]
        data_finance_output["knowledge_graph_context"] = compact_graph_for(
            "Data & Finance Agent"
        )
        data_finance_output["sql_tool_plan"] = sql_plan_for_agent(
            "Data & Finance Agent",
            contract_id=contract_id,
        )
        data_finance_output["outputs"]["finance"] = finance
        data_finance_output["handoff_to"] = "Data & Finance Agent AI/NLP Tool"
        data_finance_output["handoff_payload"] = {
            "low_margin_flag": screening["low_margin_flag"],
            "cashflow_gap_flag": finance["cashflow_gap_flag"],
            "delivery_delay_risk_flag": screening["delivery_delay_risk_flag"],
            "funding_need": finance["funding_need"],
            "bank_service_required_flag": finance["bank_service_required_flag"],
            "funding_gap": finance["funding_gap"],
            "financial_needs": finance["financial_needs"],
        }
        data_finance_output["outputs"]["finance_memory"] = self._finance_memory(
            context, screening, finance
        )
        return data_finance_output

    def _build_context(
        self,
        tables: dict[str, pd.DataFrame],
        contract_id: str,
        evaluation_date: date,
    ) -> dict[str, Any]:
        contracts = tables["04_CONTRACTS"]
        contract = row(contracts, "contract_id", contract_id)
        if not contract:
            raise ValueError(f"Contract not found: {contract_id}")

        customers = tables["03_CUSTOMERS"]
        customer = row(customers, "customer_id", contract.get("customer_id"))

        orders_all = tables["06_ORDERS"]
        orders = orders_all[
            orders_all["contract_id"].astype(str) == text(contract.get("contract_id"))
        ]

        invoices_all = tables["07_INVOICES"]
        invoices = invoices_all[
            invoices_all["customer_id"].astype(str) == text(contract.get("customer_id"))
        ]

        opc_profile = tables["02_OPC_PROFILE"]
        return {
            "tables": tables,
            "evaluation_date": evaluation_date,
            "contract": contract,
            "customer": customer or {},
            "orders": orders,
            "invoices": invoices,
            "fallback_margin": as_float(
                profile_value(opc_profile, "target_gross_margin", 0.28), 0.28
            ),
            "cash_reserve_minimum": as_float(
                profile_value(opc_profile, "cash_reserve_minimum", 550_000_000),
                550_000_000,
            ),
            "penalty_rate": as_float(
                profile_value(opc_profile, "late_delivery_penalty_rate", 0.015),
                0.015,
            ),
        }

    def _opportunity_profile(self, context: dict[str, Any]) -> dict[str, Any]:
        contract = context["contract"]
        customer = context["customer"]
        orders = context["orders"]
        return {
            "contract": {k: json_value(v) for k, v in contract.items()},
            "customer": {k: json_value(v) for k, v in customer.items()},
            "orders": records(orders),
            "linked_keys": {
                "contract_id": text(contract.get("contract_id")),
                "customer_id": text(contract.get("customer_id")),
                "order_ids": [text(v) for v in orders.get("order_id", [])],
                "service_ids": sorted(
                    {text(v) for v in orders.get("service_id", []) if text(v)}
                ),
            },
        }

    def _screening(self, context: dict[str, Any]) -> dict[str, Any]:
        contract = context["contract"]
        customer = context["customer"]
        orders = context["orders"]
        invoices = context["invoices"]
        tables = context["tables"]
        evaluation_date = context["evaluation_date"]

        missing_core = (
            clean(contract.get("contract_value")) is None
            or clean(contract.get("gross_margin")) is None
            or not text(contract.get("payment_terms"))
            or not customer
        )
        if missing_core:
            data_readiness_status = "Incomplete"
        elif orders.empty or orders["service_id"].isna().any():
            data_readiness_status = "Low Confidence"
        else:
            data_readiness_status = "Ready"

        data_governance_flag = self._data_governance_flag(tables, contract)
        has_overdue_invoice = self._has_overdue_invoice(invoices, evaluation_date)
        payment_band = self._payment_band(customer.get("payment_reliability"))
        customer_segment_fit = self._customer_segment_fit(customer.get("customer_type"))
        customer_payment_risk = self._customer_payment_risk(
            payment_band,
            has_overdue_invoice,
        )

        target_ref, target_ref_source = self._target_margin_ref(context)
        gross_margin = as_float(contract.get("gross_margin"), 0.0) or 0.0
        margin_gap = target_ref - gross_margin
        low_margin_flag = gross_margin < target_ref
        margin_gap_severity = self._margin_gap_severity(margin_gap)

        payment_terms = text(contract.get("payment_terms"))
        payment_terms_pressure = payment_terms in {
            "Performance bond required",
            "Possible LC/trade finance",
        }
        revenue_cadence_mismatch = self._revenue_cadence_mismatch(context)
        contract_discount_flag = self._contract_discount_flag(context)
        service_segment_fit = self._service_segment_fit(context)
        contract_screening_result = self._contract_screening(
            margin_gap_severity, payment_terms_pressure
        )
        gateway_flags = self._gateway_flags(
            customer_segment_fit,
            service_segment_fit,
            customer_payment_risk,
            contract_screening_result,
        )

        feasibility_status, capacity_risk_flag, province_count = self._feasibility_status(
            context
        )
        (
            delivery_delay_risk_flag,
            penalty_exposure,
            delayed_orders,
        ) = self._delivery_delay(context)
        preliminary_screening_result = self._preliminary_result(
            feasibility_status, contract_screening_result
        )

        return {
            "data_readiness_status": data_readiness_status,
            "data_governance_flag": data_governance_flag,
            "payment_reliability_band": payment_band,
            "has_overdue_invoice": has_overdue_invoice,
            "customer_segment_fit": customer_segment_fit,
            "customer_payment_risk": customer_payment_risk,
            "target_margin_ref": target_ref,
            "target_margin_ref_source": target_ref_source,
            "low_margin_flag": low_margin_flag,
            "margin_gap": margin_gap,
            "margin_gap_severity": margin_gap_severity,
            "payment_terms_pressure_flag": payment_terms_pressure,
            "revenue_cadence_mismatch_flag": revenue_cadence_mismatch,
            "contract_discount_flag": contract_discount_flag,
            "service_segment_fit": service_segment_fit,
            "contract_screening_result": contract_screening_result,
            "gateway_flags": gateway_flags,
            "feasibility_status": feasibility_status,
            "capacity_risk_flag": capacity_risk_flag,
            "province_count": province_count,
            "delivery_delay_risk_flag": delivery_delay_risk_flag,
            "penalty_exposure": penalty_exposure,
            "delayed_orders": delayed_orders,
            "preliminary_screening_result": preliminary_screening_result,
        }

    def _finance(self, context: dict[str, Any]) -> dict[str, Any]:
        contract = context["contract"]
        orders = context["orders"]
        invoices = context["invoices"]
        cashflow = context["tables"]["09_CASHFLOW"]
        cash_reserve_minimum = context["cash_reserve_minimum"]

        open_ar_status = invoices["status"].astype(str).isin({"Not issued", "Open"})
        total_open_ar = float(invoices.loc[open_ar_status, "invoice_amount"].sum())
        total_estimated_cost = (
            float(orders["estimated_cost"].sum()) if not orders.empty else 0.0
        )

        deployment_months = sorted(
            {m for m in (month_key(v) for v in orders.get("due_date", [])) if m}
        )
        monthly_contract_costs: dict[str, float] = {}
        for _, order_item in orders.iterrows():
            month = month_key(order_item.get("due_date"))
            if not month:
                continue
            monthly_contract_costs[month] = monthly_contract_costs.get(month, 0.0) + (
                as_float(order_item.get("estimated_cost"), 0.0) or 0.0
            )
        cashflow_gap_months = []
        cashflow_gap_warning_months = []
        for month in deployment_months:
            rows = cashflow[cashflow["month"].astype(str).str[:7] == month]
            for _, cash_row in rows.iterrows():
                minimum = as_float(
                    cash_row.get("cash_reserve_minimum"), cash_reserve_minimum
                )
                closing_cash = as_float(cash_row.get("projected_closing_cash"), 0.0)
                if closing_cash < minimum:
                    contract_month_cost = monthly_contract_costs.get(month, 0.0)
                    gap_item = {
                        "month": month,
                        "projected_closing_cash": closing_cash,
                        "cash_reserve_minimum": minimum,
                        "reserve_gap_amount": minimum - closing_cash,
                        "contract_month_estimated_cost": contract_month_cost,
                        "materiality_threshold": MATERIAL_CASHFLOW_COST_THRESHOLD,
                    }
                    if contract_month_cost >= MATERIAL_CASHFLOW_COST_THRESHOLD:
                        cashflow_gap_months.append(gap_item)
                    else:
                        cashflow_gap_warning_months.append(gap_item)
        cashflow_gap_flag = bool(cashflow_gap_months)

        text_to_scan = " ".join(
            [text(contract.get("payment_terms"))]
            + [text(value) for value in orders.get("delivery_note", [])]
        )
        bank_service_required_flag = bool(BANK_SIGNAL_PATTERN.search(text_to_scan))
        revenue_cadence_mismatch_flag = self._revenue_cadence_mismatch(context)
        funding_need = (
            "Required"
            if cashflow_gap_flag
            or total_open_ar >= total_estimated_cost
            or bank_service_required_flag
            or revenue_cadence_mismatch_flag
            else "Not Needed"
        )
        cashflow_summary = self._cashflow_summary(
            cashflow_gap_months,
            total_open_ar,
            cash_reserve_minimum,
        )
        enriched_orders = self._enriched_orders(
            context,
            cashflow_summary.get("total_funding_gap", 0.0),
        )
        funding_gap = self._funding_gap(
            context=context,
            total_open_ar=total_open_ar,
            total_estimated_cost=total_estimated_cost,
            cashflow_gap_months=cashflow_gap_months,
            cashflow_gap_flag=cashflow_gap_flag,
            bank_service_required_flag=bank_service_required_flag,
            revenue_cadence_mismatch_flag=revenue_cadence_mismatch_flag,
            enriched_orders=enriched_orders,
            cashflow_summary=cashflow_summary,
        )
        financial_needs = self._financial_needs(enriched_orders, funding_gap)

        return {
            "total_open_ar": total_open_ar,
            "total_estimated_cost": total_estimated_cost,
            "deployment_months": deployment_months,
            "orders": enriched_orders,
            "cashflow_summary": cashflow_summary,
            "cashflow_gap_flag": cashflow_gap_flag,
            "cashflow_gap_months": cashflow_gap_months,
            "cashflow_gap_warning_months": cashflow_gap_warning_months,
            "bank_service_required_flag": bank_service_required_flag,
            "revenue_cadence_mismatch_flag": revenue_cadence_mismatch_flag,
            "funding_need": funding_need,
            "funding_gap": funding_gap,
            "financial_needs": financial_needs,
            "financial_need_labels": [
                item["need_type"] for item in financial_needs if item.get("need_type")
            ],
            "required_prechecks": self._required_prechecks(funding_gap),
        }

    def _cashflow_summary(
        self,
        cashflow_gap_months: list[dict[str, Any]],
        total_open_ar: float,
        cash_reserve_minimum: float,
    ) -> dict[str, Any]:
        return {
            "months_below_reserve": [
                text(item.get("month")) for item in cashflow_gap_months if item.get("month")
            ],
            "total_funding_gap": sum(
                as_float(item.get("reserve_gap_amount"), 0.0) or 0.0
                for item in cashflow_gap_months
            ),
            "open_receivables": total_open_ar,
            "cash_reserve_minimum": cash_reserve_minimum,
        }

    def _enriched_orders(
        self,
        context: dict[str, Any],
        cashflow_gap_amount: float,
    ) -> list[dict[str, Any]]:
        orders = context["orders"]
        contract = context["contract"]
        contract_value = as_float(contract.get("contract_value"), 0.0) or 0.0
        if orders.empty:
            return []

        staged_rows: list[dict[str, Any]] = []
        working_capital_rows: list[dict[str, Any]] = []
        for _, order_item in orders.iterrows():
            order_dict = {k: json_value(v) for k, v in order_item.to_dict().items()}
            revenue = as_float(
                order_item.get("order_revenue")
                or order_item.get("revenue")
                or order_item.get("contract_value"),
                0.0,
            ) or 0.0
            estimated_cost = as_float(order_item.get("estimated_cost"), 0.0) or 0.0
            computed_margin = (
                (revenue - estimated_cost) / revenue
                if revenue > 0 and estimated_cost >= 0
                else as_float(contract.get("gross_margin"), None)
            )
            need_type = self._order_need_type(contract, order_item)
            staged = {
                **order_dict,
                "order_revenue": revenue,
                "estimated_cost": estimated_cost,
                "computed_margin": computed_margin,
                "financial_need": self._need_label(need_type),
                "need_type": need_type,
                "need_amount_estimate": 0.0,
            }
            if need_type == "working_capital":
                working_capital_rows.append(staged)
            staged_rows.append(staged)

        total_working_cost = sum(
            as_float(item.get("estimated_cost"), 0.0) or 0.0
            for item in working_capital_rows
        )
        for item in staged_rows:
            need_type = text(item.get("need_type"))
            if need_type == "performance_bond":
                item["need_amount_estimate"] = contract_value * PERFORMANCE_BOND_ESTIMATE_RATE
            elif need_type == "trade_finance":
                item["need_amount_estimate"] = (
                    as_float(item.get("order_revenue"), 0.0) or contract_value
                )
            elif need_type == "working_capital":
                cost = as_float(item.get("estimated_cost"), 0.0) or 0.0
                if cashflow_gap_amount > 0 and total_working_cost > 0:
                    item["need_amount_estimate"] = cashflow_gap_amount * cost / total_working_cost
                else:
                    item["need_amount_estimate"] = cost
            item.pop("need_type", None)
        return staged_rows

    def _order_need_type(self, contract: dict[str, Any], order_item: Any) -> str:
        searchable = " ".join(
            [
                text(contract.get("payment_terms")),
                text(contract.get("description")),
                text(order_item.get("delivery_note")),
            ]
        ).lower()
        if re.search(r"\b(performance bond|bond)\b|bao lanh|bảo lãnh", searchable):
            return "performance_bond"
        if re.search(r"\b(lc|letter of credit|trade finance)\b", searchable):
            return "trade_finance"
        if re.search(r"\b(working capital|cashflow|cash flow|vốn lưu động)\b", searchable):
            return "working_capital"
        return "none"

    def _funding_gap(
        self,
        context: dict[str, Any],
        total_open_ar: float,
        total_estimated_cost: float,
        cashflow_gap_months: list[dict[str, Any]],
        cashflow_gap_flag: bool,
        bank_service_required_flag: bool,
        revenue_cadence_mismatch_flag: bool,
        enriched_orders: list[dict[str, Any]],
        cashflow_summary: dict[str, Any],
    ) -> dict[str, Any]:
        contract = context["contract"]
        orders = context["orders"]
        contract_id = text(contract.get("contract_id"))
        payment_terms = text(contract.get("payment_terms"))
        contract_value = as_float(contract.get("contract_value"), 0.0) or 0.0
        delivery_notes = [text(value) for value in orders.get("delivery_note", [])]
        searchable = " ".join(
            [payment_terms, text(contract.get("description")), *delivery_notes]
        ).lower()

        needs: list[dict[str, Any]] = []
        order_need_amounts: dict[str, float] = {}
        for order_item in enriched_orders:
            need_type = self._need_key(text(order_item.get("financial_need")))
            if need_type == "none":
                continue
            order_need_amounts[need_type] = order_need_amounts.get(
                need_type, 0.0
            ) + (as_float(order_item.get("need_amount_estimate"), 0.0) or 0.0)

        if re.search(r"\b(performance bond|bond)\b|bảo lãnh|bao lanh", searchable):
            needs.append(
                {
                    "type": "performance_bond",
                    "required_amount": contract_value,
                    "currency": "VND",
                    "reason": [
                        "Delivery note hoặc payment_terms yêu cầu bảo lãnh thực hiện hợp đồng.",
                        "Nhu cầu này không phải thiếu tiền mặt mà là nghĩa vụ bảo lãnh trước khi ký/triển khai.",
                    ],
                    "source_evidence": self._evidence_lines(
                        contract_id,
                        [
                            ("04_CONTRACTS.payment_terms", payment_terms),
                            ("04_CONTRACTS.contract_value", contract_value),
                            ("06_ORDERS.delivery_note", delivery_notes),
                        ],
                    ),
                    "missing_documents": [],
                    "confidence": 0.86,
                }
            )

        if re.search(r"\b(LC|letter of credit|trade finance)\b", searchable, re.I):
            missing_documents = []
            if "supplier confirmation" not in searchable:
                missing_documents.append("supplier confirmation")
            needs.append(
                {
                    "type": "trade_finance",
                    "required_amount": contract_value,
                    "currency": "VND",
                    "reason": [
                        "Payment terms hoặc delivery note có tín hiệu LC/trade finance.",
                        "Decision Agent cần kiểm tra precheck LC/trade finance trước khi lập hồ sơ.",
                    ],
                    "source_evidence": self._evidence_lines(
                        contract_id,
                        [
                            ("04_CONTRACTS.payment_terms", payment_terms),
                            ("04_CONTRACTS.contract_value", contract_value),
                            ("06_ORDERS.delivery_note", delivery_notes),
                        ],
                    ),
                    "missing_documents": missing_documents,
                    "confidence": 0.80 if missing_documents else 0.88,
                }
            )

        if cashflow_gap_flag or total_open_ar >= total_estimated_cost or revenue_cadence_mismatch_flag:
            gap_amounts = [
                as_float(item.get("reserve_gap_amount"), 0.0) or 0.0
                for item in cashflow_gap_months
            ]
            required_amount = max(
                [0.0, *gap_amounts, min(total_open_ar, total_estimated_cost)]
            )
            reasons = []
            if cashflow_gap_flag:
                months = ", ".join(
                    text(item.get("month")) for item in cashflow_gap_months if item.get("month")
                )
                reasons.append(
                    f"Cashflow gap ở tháng {months} làm projected cash thấp hơn cash reserve minimum."
                )
            if total_open_ar >= total_estimated_cost and total_estimated_cost > 0:
                reasons.append(
                    "Open AR lớn hơn hoặc bằng estimated cost nên có áp lực vốn lưu động."
                )
            if revenue_cadence_mismatch_flag:
                reasons.append(
                    "Nhịp thu tiền và nhịp giao hàng không khớp, cần kiểm tra vốn lưu động."
                )
            needs.append(
                {
                    "type": "working_capital",
                    "required_amount": required_amount,
                    "currency": "VND",
                    "reason": reasons or ["Finance Agent phát hiện áp lực vốn lưu động."],
                    "source_evidence": self._evidence_lines(
                        contract_id,
                        [
                            ("07_INVOICES.open_ar", total_open_ar),
                            ("06_ORDERS.estimated_cost_total", total_estimated_cost),
                            ("09_CASHFLOW.cashflow_gap_months", cashflow_gap_months),
                        ],
                    ),
                    "missing_documents": [],
                    "confidence": 0.84 if cashflow_gap_flag else 0.72,
                }
            )

        for need in needs:
            need_type = text(need.get("type"))
            if order_need_amounts.get(need_type, 0.0) > 0:
                need["required_amount"] = order_need_amounts[need_type]
            elif need_type == "performance_bond":
                need["required_amount"] = contract_value * PERFORMANCE_BOND_ESTIMATE_RATE
            elif need_type == "working_capital":
                need["required_amount"] = max(
                    as_float(need.get("required_amount"), 0.0) or 0.0,
                    as_float(cashflow_summary.get("total_funding_gap"), 0.0) or 0.0,
                )

        priority = {
            "performance_bond": 3,
            "trade_finance": 2,
            "working_capital": 1,
        }
        unique_needs: dict[str, dict[str, Any]] = {}
        for need in needs:
            unique_needs.setdefault(need["type"], need)
        ordered = sorted(
            unique_needs.values(),
            key=lambda item: (
                priority.get(text(item.get("type")), 0),
                as_float(item.get("confidence"), 0.0) or 0.0,
            ),
            reverse=True,
        )
        primary = ordered[0] if ordered else None

        return {
            "needs": ordered,
            "primary_need_type": primary["type"] if primary else "none",
            "primary_need_label": self._need_label(primary["type"]) if primary else "None",
            "funding_gap_amount": primary["required_amount"] if primary else 0.0,
            "overall_confidence": primary["confidence"] if primary else 0.0,
            "bank_service_required_flag": bank_service_required_flag,
            "summary": (
                [
                    f"Primary need: {primary['type']} with confidence {primary['confidence']}."
                ]
                + list(primary.get("reason", []))[:2]
                if primary
                else ["No financing/bank product need detected from supplied evidence."]
            ),
        }

    def _financial_needs(
        self,
        enriched_orders: list[dict[str, Any]],
        funding_gap: dict[str, Any],
    ) -> list[dict[str, Any]]:
        needs = []
        for order_item in enriched_orders:
            need_type = text(order_item.get("financial_need"))
            if not need_type or need_type == "None":
                continue
            needs.append(
                {
                    "need_type": need_type,
                    "amount_estimate": as_float(
                        order_item.get("need_amount_estimate"), 0.0
                    )
                    or 0.0,
                    "linked_order": text(order_item.get("order_id")),
                }
            )
        if needs:
            return needs
        return [
            {
                "need_type": self._need_label(text(need.get("type"))),
                "amount_estimate": as_float(need.get("required_amount"), 0.0) or 0.0,
                "linked_order": None,
            }
            for need in funding_gap.get("needs", [])
            if text(need.get("type")) != "none"
        ]

    def _required_prechecks(self, funding_gap: dict[str, Any]) -> list[str]:
        api_by_need = {
            "performance_bond": "API-002",
            "trade_finance": "API-003",
            "working_capital": "API-005",
        }
        prechecks = []
        for need in funding_gap.get("needs", []):
            api_id = api_by_need.get(text(need.get("type")))
            if api_id and api_id not in prechecks:
                prechecks.append(api_id)
        return prechecks

    def _need_label(self, need_type: str) -> str:
        labels = {
            "performance_bond": "Performance Bond",
            "trade_finance": "LC / Trade Finance",
            "working_capital": "Working Capital",
            "none": "None",
        }
        return labels.get(text(need_type), text(need_type) or "None")

    def _need_key(self, need_label: str) -> str:
        normalized = text(need_label).lower()
        if "performance bond" in normalized:
            return "performance_bond"
        if "trade" in normalized or "lc" in normalized:
            return "trade_finance"
        if "working capital" in normalized:
            return "working_capital"
        return "none"

    def _finance_memory(
        self,
        context: dict[str, Any],
        screening: dict[str, Any],
        finance: dict[str, Any],
    ) -> dict[str, Any]:
        contract = context["contract"]
        customer = context["customer"]
        orders = context["orders"]
        triggered_rules = []
        if screening.get("low_margin_flag"):
            triggered_rules.append("RR-003")
        if finance.get("cashflow_gap_flag"):
            triggered_rules.append("RR-002")
        return {
            "contract": {k: json_value(v) for k, v in contract.items()},
            "customer": {k: json_value(v) for k, v in customer.items()},
            "orders": records(orders),
            "financial_metrics": {
                "gross_margin": json_value(contract.get("gross_margin")),
                "target_margin": screening.get("target_margin_ref"),
                "funding_gap": finance["funding_gap"].get("funding_gap_amount", 0.0),
                "total_open_ar": finance.get("total_open_ar"),
                "total_estimated_cost": finance.get("total_estimated_cost"),
            },
            "funding_gap": finance["funding_gap"],
            "financial_needs": finance["financial_needs"],
            "candidate_bank_products": [],
            "triggered_rules": triggered_rules,
            "required_prechecks": finance["required_prechecks"],
        }

    def _evidence_lines(
        self,
        contract_id: str,
        values: list[tuple[str, Any]],
    ) -> list[str]:
        evidence = []
        for field, value in values:
            if isinstance(value, list):
                cleaned = [text(item) for item in value if text(item)]
                if cleaned:
                    evidence.append(f"{field}={'; '.join(cleaned[:3])}")
            elif value not in {None, ""}:
                evidence.append(f"{field}={json_value(value)}")
        if contract_id:
            evidence.insert(0, f"04_CONTRACTS.contract_id={contract_id}")
        return evidence[:6]

    def _data_governance_flag(
        self, tables: dict[str, pd.DataFrame], contract: dict[str, Any]
    ) -> str | None:
        customer_id = text(contract.get("customer_id"))
        bank_txn = tables["08_BANK_TXN"]
        contracts = tables["04_CONTRACTS"]
        has_bank_txn = not bank_txn[
            bank_txn["counterparty_id"].astype(str) == customer_id
        ].empty
        has_customer_contract = not contracts[
            contracts["customer_id"].astype(str) == customer_id
        ].empty
        return "Chua formalize hop dong" if has_bank_txn and not has_customer_contract else None

    def _has_overdue_invoice(
        self, invoices: pd.DataFrame, evaluation_date: date
    ) -> bool:
        open_overdue = invoices[
            (invoices["status"].astype(str) == "Open")
            & invoices["due_date"].apply(
                lambda value: (as_date(value) or date.max) < evaluation_date
            )
        ]
        return not open_overdue.empty

    def _payment_band(self, payment_reliability: Any) -> str:
        value = clean(payment_reliability)
        if value is None:
            return "Unknown"
        value = float(value)
        if value >= 0.675:
            return "High"
        if value >= 0.50:
            return "Medium"
        return "Low"

    def _customer_segment_fit(self, customer_type: Any) -> str:
        customer_type = text(customer_type)
        if not customer_type:
            return "Unknown"
        return "Fit" if customer_type in TARGET_CUSTOMER_SEGMENTS else "Out of Scope"

    def _customer_payment_risk(
        self, payment_band: str, has_overdue_invoice: bool
    ) -> str:
        if payment_band == "Unknown":
            return "Unknown"
        if has_overdue_invoice:
            return "High"
        if payment_band == "High":
            return "Low"
        if payment_band == "Medium":
            return "Medium"
        return "High"

    def _target_margin_ref(self, context: dict[str, Any]) -> tuple[float, str]:
        orders = context["orders"]
        products = context["tables"]["05_PRODUCTS"]
        fallback_margin = context["fallback_margin"]
        if orders.empty:
            return fallback_margin, "02_OPC_PROFILE.target_gross_margin"

        weighted_total = 0.0
        revenue_total = 0.0
        service_ids = []
        for _, order_item in orders.iterrows():
            product = row(products, "service_id", order_item.get("service_id"))
            if not product:
                continue
            revenue = as_float(order_item.get("order_revenue"), 0.0) or 0.0
            target_margin = as_float(product.get("target_margin"), fallback_margin) or fallback_margin
            weighted_total += revenue * target_margin
            revenue_total += revenue
            service_ids.append(text(order_item.get("service_id")))

        if revenue_total <= 0:
            return fallback_margin, "02_OPC_PROFILE.target_gross_margin"
        if len(set(service_ids)) == 1:
            return weighted_total / revenue_total, f"05_PRODUCTS.target_margin:{service_ids[0]}"
        return (
            weighted_total / revenue_total,
            "weighted_average(06_ORDERS.order_revenue,05_PRODUCTS.target_margin)",
        )

    def _margin_gap_severity(self, gap: float) -> str:
        if gap <= 0:
            return "None"
        if gap < 0.03:
            return "Minor"
        if gap <= 0.06:
            return "Moderate"
        return "Severe"

    def _revenue_cadence_mismatch(self, context: dict[str, Any]) -> bool:
        contract = context["contract"]
        orders = context["orders"]
        products = context["tables"]["05_PRODUCTS"]
        payment_terms = text(contract.get("payment_terms"))
        for _, order_item in orders.iterrows():
            product = row(products, "service_id", order_item.get("service_id"))
            if product and text(product.get("pricing_model")) == "Monthly subscription":
                if payment_terms != "Monthly payment":
                    return True
        return False

    def _contract_discount_flag(self, context: dict[str, Any]) -> bool | str:
        contract = context["contract"]
        orders = context["orders"]
        products = context["tables"]["05_PRODUCTS"]
        flags = []
        for _, order_item in orders.iterrows():
            product = row(products, "service_id", order_item.get("service_id"))
            if product and text(product.get("pricing_model")) == "Project":
                flags.append(
                    as_float(contract.get("contract_value"), 0.0)
                    != as_float(product.get("list_price"), 0.0)
                )
        return any(flags) if flags else "Not Applicable"

    def _service_segment_fit(self, context: dict[str, Any]) -> str:
        customer = context["customer"]
        orders = context["orders"]
        products = context["tables"]["05_PRODUCTS"]
        fits = []
        for _, order_item in orders.iterrows():
            product = row(products, "service_id", order_item.get("service_id"))
            if not product:
                fits.append("Unknown")
                continue
            matched = segment_matches(product.get("target_segment"), customer)
            fits.append("Unknown" if matched is None else "Fit" if matched else "Mismatch")

        if not fits:
            return "Unknown"
        if "Mismatch" in fits:
            return "Mismatch"
        if "Unknown" in fits:
            return "Unknown"
        return "Fit"

    def _contract_screening(
        self, margin_gap_severity: str, payment_terms_pressure: bool
    ) -> str:
        margin_pressure = margin_gap_severity in {"Moderate", "Severe"}
        if margin_pressure and payment_terms_pressure:
            return "Margin Pressure + Payment Term Pressure"
        if margin_pressure:
            return "Margin Pressure"
        if payment_terms_pressure:
            return "Payment Term Pressure"
        return "Pass"

    def _gateway_flags(
        self,
        customer_segment_fit: str,
        service_segment_fit: str,
        customer_payment_risk: str,
        contract_screening_result: str,
    ) -> list[str]:
        flags = []
        if customer_segment_fit == "Out of Scope":
            flags.append("Need Clarification: xac nhan lai phan khuc khach hang.")
        if customer_segment_fit == "Unknown":
            flags.append("Need Clarification: thieu customer_type de xac nhan phan khuc.")
        if service_segment_fit == "Mismatch":
            flags.append("Need Clarification: xac nhan viec ban dung dich vu cho dung phan khuc.")
        if service_segment_fit == "Unknown":
            flags.append("Need Clarification: thieu service/product segment de xac nhan fit.")
        if customer_payment_risk == "High":
            flags.append("Founder Review Required: customer_payment_risk = High.")
        if contract_screening_result != "Pass" and not flags:
            flags.append(f"Carry warning: {contract_screening_result}.")
        return flags

    def _extract_province_count(self, description: Any) -> int | None:
        raw = text(description)
        match = re.search(r"(\d+)\s*[- ]?\s*province", raw, re.IGNORECASE)
        if match:
            return int(match.group(1))
        match = re.search(r"(\d+)\s*(tỉnh|tinh)", raw, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    def _base_feasibility(self, orders: pd.DataFrame) -> str:
        statuses = [text(v) for v in orders.get("status", [])]
        if not statuses:
            return "Need Clarification"
        if any(status in {"At risk", "Delayed"} for status in statuses):
            return "Not Feasible"
        pending_count = statuses.count("Pending approval")
        due_dates = sorted(d for d in (as_date(v) for v in orders.get("due_date", [])) if d)
        close_due_dates = any(
            (later - earlier).days <= 30
            for earlier, later in zip(due_dates, due_dates[1:])
        )
        planned_only = all(status == "Planned" for status in statuses)
        planned_pending_only = all(status in {"Planned", "Pending approval"} for status in statuses)

        if pending_count > 0 or close_due_dates:
            return "Feasible with Conditions"
        if planned_only:
            return "Feasible" if len(statuses) <= 1 else "Feasible with Conditions"
        if planned_pending_only:
            return "Feasible with Conditions"
        return "Feasible"

    def _feasibility_status(self, context: dict[str, Any]) -> tuple[str, bool, int | None]:
        contract = context["contract"]
        orders = context["orders"]
        alerts = context["tables"]["14_ALERTS"]
        province_count = self._extract_province_count(contract.get("description"))
        related_alerts = alerts[
            alerts["related_record"].astype(str) == text(contract.get("contract_id"))
        ]
        capacity_risk = bool(
            (province_count is not None and province_count >= 10)
            or not related_alerts.empty
        )
        status = self._base_feasibility(orders)
        if capacity_risk:
            status = "Feasible with Conditions"
        return status, capacity_risk, province_count

    def _delivery_delay(self, context: dict[str, Any]) -> tuple[bool, float, list[dict[str, Any]]]:
        orders = context["orders"]
        penalty_rate = context["penalty_rate"]
        evaluation_date = context["evaluation_date"]
        delayed = []
        exposure = 0.0
        for _, order_item in orders.iterrows():
            due = as_date(order_item.get("due_date"))
            status = text(order_item.get("status"))
            if due is None or status not in {"At risk", "Delayed"}:
                continue
            delay_days = (evaluation_date - due).days
            if delay_days > 7:
                amount = (as_float(order_item.get("order_revenue"), 0.0) or 0.0) * penalty_rate * delay_days
                exposure += amount
                delayed.append(
                    {
                        "order_id": text(order_item.get("order_id")),
                        "delay_days": delay_days,
                        "penalty_exposure": amount,
                    }
                )
        return bool(delayed), exposure, delayed

    def _preliminary_result(self, feasibility_status: str, screening_result: str) -> str:
        if feasibility_status == "Not Feasible":
            return "Hold"
        if feasibility_status == "Feasible" and screening_result == "Pass":
            return "Shortlist for Deep Assessment"
        if feasibility_status == "Feasible with Conditions" or screening_result != "Pass":
            return "Conditional Shortlist"
        return "Need Clarification"
