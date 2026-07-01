"""
Flask Web Server
================
Serves the data viewer web interface with table selection and data loading.
"""

from flask import Flask, render_template, request, jsonify
from connector import get_connector
from functions import mask_sensitive_data

app = Flask(__name__)


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

        # Convert to JSON-friendly format
        columns = list(display_df.columns)
        rows = display_df.fillna("").astype(str).values.tolist()
        total_rows = len(rows)

        # Schema info
        schema = []
        for _, row in schema_df.iterrows():
            schema.append({
                "column": row.get("column_name", ""),
                "type": row.get("column_type", ""),
                "nullable": row.get("null", ""),
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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
