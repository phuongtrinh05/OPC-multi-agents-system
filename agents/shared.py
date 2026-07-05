from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import pandas as pd


TARGET_OPPORTUNITY_STATUSES = {"Negotiation", "Pending expansion"}
TARGET_CUSTOMER_SEGMENTS = {"SME", "Cooperative", "Household"}


def clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value):
        return None
    return value


def text(value: Any) -> str:
    value = clean(value)
    return "" if value is None else str(value).strip()


def as_float(value: Any, default: float | None = 0.0) -> float | None:
    value = clean(value)
    if value is None or value == "":
        return default
    return float(value)


def as_date(value: Any) -> date | None:
    value = clean(value)
    if value is None or value == "":
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def month_key(value: Any) -> str | None:
    parsed = as_date(value)
    if parsed is None:
        raw = text(value)
        return raw[:7] if raw else None
    return f"{parsed.year:04d}-{parsed.month:02d}"


def bool_text(value: bool) -> str:
    return "TRUE" if value else "FALSE"


def row(df: pd.DataFrame, column: str, value: Any) -> dict[str, Any] | None:
    matches = df[df[column].astype(str) == str(value)]
    if matches.empty:
        return None
    return matches.iloc[0].to_dict()


def json_value(value: Any) -> Any:
    value = clean(value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{k: json_value(v) for k, v in item.items()} for item in df.to_dict("records")]


def profile_value(opc_profile: pd.DataFrame, field: str, default: Any = None) -> Any:
    match = opc_profile[opc_profile["field"].astype(str) == field]
    if match.empty:
        return default
    return clean(match.iloc[0]["value"])


def risk_rule(risk_rules: pd.DataFrame, rule_id: str) -> dict[str, Any]:
    risk = row(risk_rules, "rule_id", rule_id) or {}
    return {
        "rule_id": rule_id,
        "risk_type": text(risk.get("risk_type")),
        "severity": text(risk.get("severity")),
        "required_action": text(risk.get("required_action")),
        "owner_agent": text(risk.get("owner_agent")),
    }


def segment_matches(target_segment: Any, customer: dict[str, Any]) -> bool | None:
    target = text(target_segment)
    customer_type = text(customer.get("customer_type"))
    industry = text(customer.get("industry"))
    if not target or not customer_type:
        return None

    if "/" in target:
        return customer_type.lower() in {
            part.strip().lower() for part in target.split("/")
        }

    target_lower = target.lower()
    if customer_type.lower() in target_lower:
        return True

    if customer_type and industry:
        combo_a = f"{industry} {customer_type}".lower()
        combo_b = f"{customer_type} {industry}".lower()
        return target_lower in {combo_a, combo_b} or all(
            token.lower() in target_lower for token in [customer_type, industry]
        )

    return False
