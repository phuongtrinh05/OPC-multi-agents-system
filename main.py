"""
Flask Web Server
================
Serves the data viewer web interface with table selection and data loading.
"""

from datetime import date
import math
from uuid import uuid4

from flask import Flask, render_template, request, jsonify
import pandas as pd
from connector import get_connector
from functions import mask_sensitive_data
from opportunity_agent import (
    evaluate_opportunity,
    list_opportunities,
    run_ai_reasoning_step,
    run_data_finance_step,
    run_decision_step,
    run_risk_step,
)

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
WORKFLOW_SESSIONS = {}


@app.route("/")
def index():
    """Serve the main data viewer page."""
    return render_template("index.html")


@app.route("/api/tables", methods=["GET"])
def get_tables():
    """Return list of available tables in MotherDuck."""
    try:
        conn = get_connector()
        tables = conn.list_tables()
        return jsonify({"tables": tables})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/table/<table_name>", methods=["GET"])
def get_table_data(table_name):
    """Load data from a specific table.

    Query params:
        limit: max rows to return (default 100, max 10000)
        mask: whether to mask sensitive data (default true)
    """
    try:
        limit = request.args.get("limit", 100, type=int)
        mask = request.args.get("mask", "true").lower() == "true"

        conn = get_connector()

        # Get table data
        df = conn.read_table(table_name, limit)

        # Get table schema
        schema_df = conn.describe_table(table_name)

        # Apply masking if enabled
        if mask:
            display_df = mask_sensitive_data(df)
        else:
            display_df = df

        # Convert to JSON-friendly format. Browser JSON parsing rejects NaN.
        columns = list(display_df.columns)
        clean_df = display_df.astype(object).where(pd.notna(display_df), "")
        rows = [
            [_json_safe_value(cell) for cell in row]
            for row in clean_df.values.tolist()
        ]
        total_rows = len(rows)

        # Schema info
        schema = []
        for _, row in schema_df.iterrows():
            schema.append({
                "column": _json_safe_value(row.get("column_name", "")),
                "type": _json_safe_value(row.get("column_type", "")),
                "nullable": _json_safe_value(row.get("null", "")),
            })

        return jsonify({
            "table_name": table_name,
            "columns": columns,
            "rows": rows,
            "total_rows": total_rows,
            "limit": limit,
            "schema": schema,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/opportunities", methods=["GET"])
def get_opportunities():
    """Return current business opportunities for the OPC agent workflow."""
    try:
        return jsonify({"opportunities": list_opportunities()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/opportunity/<contract_id>/decision", methods=["GET"])
def get_opportunity_decision(contract_id):
    """Run the opportunity agent and return a founder-facing Decision Card."""
    try:
        evaluation_date_raw = request.args.get("evaluation_date")
        evaluation_date = None
        if evaluation_date_raw:
            from datetime import date

            evaluation_date = date.fromisoformat(evaluation_date_raw)

        return jsonify(evaluate_opportunity(contract_id, evaluation_date))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/workflow/start", methods=["POST"])
def start_workflow():
    """Start a real HITL workflow session by running only Data & Finance Agent."""
    try:
        payload = request.get_json(silent=True) or {}
        contract_id = payload.get("contract_id")
        if not contract_id:
            return jsonify({"error": "contract_id is required"}), 400

        evaluation_date = _evaluation_date(payload.get("evaluation_date"))
        profile, data_finance_output = run_data_finance_step(
            contract_id,
            evaluation_date,
        )
        workflow_id = str(uuid4())
        WORKFLOW_SESSIONS[workflow_id] = {
            "contract_id": contract_id,
            "evaluation_date": profile["evaluation_date"],
            "data_finance_output": data_finance_output,
            "ai_output": None,
            "risk_output": None,
            "decision_output": None,
            "current_step": "data_finance",
        }
        profile.update(
            {
                "workflow_id": workflow_id,
                "current_step": "data_finance",
                "next_required_human_gate": "approve_data_intake",
            }
        )
        return jsonify(profile)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/workflow/<workflow_id>/ai-reasoning", methods=["POST"])
def workflow_ai_reasoning(workflow_id):
    """Run Data & Finance Agent finance pass plus its internal AI/NLP tool."""
    try:
        session = _workflow_session(workflow_id)
        evaluation_date = date.fromisoformat(session["evaluation_date"])
        profile, ai_output = run_ai_reasoning_step(
            session["contract_id"],
            session["data_finance_output"],
            evaluation_date,
        )
        session["ai_output"] = ai_output
        session["current_step"] = "ai_reasoning"
        profile.update(
            {
                "workflow_id": workflow_id,
                "current_step": "data_finance_ai_tool",
                "next_required_human_gate": None,
            }
        )
        return jsonify(profile)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/workflow/<workflow_id>/risk", methods=["POST"])
def workflow_risk(workflow_id):
    """Run Risk & Compliance Agent after Data & Finance handoff."""
    try:
        session = _workflow_session(workflow_id)
        if not session.get("ai_output"):
            return jsonify({"error": "AI reasoning step has not run yet"}), 409

        evaluation_date = date.fromisoformat(session["evaluation_date"])
        profile, risk_output = run_risk_step(
            session["contract_id"],
            session["data_finance_output"],
            evaluation_date,
        )
        session["risk_output"] = risk_output
        session["current_step"] = "risk"
        profile["openai_reasoning"] = session["ai_output"]["outputs"][
            "openai_reasoning"
        ]
        profile.update(
            {
                "workflow_id": workflow_id,
                "current_step": "risk",
                "next_required_human_gate": "approve_risk_review",
            }
        )
        return jsonify(profile)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/workflow/<workflow_id>/decision", methods=["POST"])
def workflow_decision(workflow_id):
    """Run Decision & Partner Agent only after Risk HITL approval."""
    try:
        session = _workflow_session(workflow_id)
        if not session.get("risk_output"):
            return jsonify({"error": "Risk step has not run yet"}), 409

        evaluation_date = date.fromisoformat(session["evaluation_date"])
        profile, risk_output, decision_output = run_decision_step(
            session["contract_id"],
            session["data_finance_output"],
            session["risk_output"],
            evaluation_date,
        )
        session["risk_output"] = risk_output
        session["decision_output"] = decision_output
        session["current_step"] = "decision"
        profile["openai_reasoning"] = session["ai_output"]["outputs"][
            "openai_reasoning"
        ]
        profile.update(
            {
                "workflow_id": workflow_id,
                "current_step": "decision",
                "next_required_human_gate": "founder_final_approval",
            }
        )
        return jsonify(profile)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _evaluation_date(raw):
    return date.fromisoformat(raw) if raw else None


def _workflow_session(workflow_id):
    session = WORKFLOW_SESSIONS.get(workflow_id)
    if not session:
        raise ValueError("Workflow session not found. Please start workflow again.")
    return session


def _json_safe_value(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return ""
    return str(value)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
