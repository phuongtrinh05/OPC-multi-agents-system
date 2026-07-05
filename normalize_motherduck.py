from __future__ import annotations

from typing import Dict, List

from connector import MotherDuckExcelUploader, quote_identifier, DEFAULT_SCHEMA


# =========================
# 1. DANH SÁCH CỘT CẦN CHUẨN HÓA
# =========================

DATE_COLUMNS: Dict[str, List[str]] = {
    "04_CONTRACTS": [
        "start_date",
        "end_date",
    ],
    "06_ORDERS": [
        "order_date",
        "due_date",
    ],
    "07_INVOICES": [
        "issue_date",
        "due_date",
        "paid_date",
    ],
    "08_BANK_TXN": [
        "txn_date",
    ],
    "14_ALERTS": [
        "alert_date",
    ],
}


MONEY_COLUMNS: Dict[str, List[str]] = {
    "04_CONTRACTS": [
        "contract_value",
    ],
    "05_PRODUCTS": [
        "list_price",
    ],
    "06_ORDERS": [
        "order_revenue",
        "estimated_cost",
    ],
    "07_INVOICES": [
        "invoice_amount",
    ],
    "08_BANK_TXN": [
        "amount",
    ],
    "09_CASHFLOW": [
        "expected_cash_in",
        "expected_cash_out",
        "direct_cost",
        "opex",
        "cash_reserve_minimum",
        "projected_closing_cash",
    ],
    "10_CREDIT_PROFILE": [
        "requested_amount",
    ],
    "11_BANK_PRODUCTS": [
        "minimum_amount",
    ],
}


RATIO_COLUMNS: Dict[str, List[str]] = {
    "03_CUSTOMERS": [
        "payment_reliability",
    ],
    "04_CONTRACTS": [
        "gross_margin",
    ],
    "05_PRODUCTS": [
        "target_margin",
    ],
    "10_CREDIT_PROFILE": [
        "eligibility_score",
    ],
    "11_BANK_PRODUCTS": [
        "annual_rate_or_fee",
        "processing_fee_rate",
        "collateral_ratio",
    ],
}


RISK_SCORE_COLUMNS: Dict[str, List[str]] = {
    "08_BANK_TXN": [
        "transaction_risk_score",
    ],
    "14_ALERTS": [
        "risk_score",
    ],
}


TEXT_COLUMNS: Dict[str, List[str]] = {
    "00_GUIDE": [
        "section",
        "content",
    ],
    "01_README": [
        "section",
        "content",
    ],
    "02_OPC_PROFILE": [
        "field",
        "value",
    ],
    "03_CUSTOMERS": [
        "customer_id",
        "customer_name",
        "customer_type",
        "province",
        "industry",
        "strategic_value",
        "revenue_model",
        "banking_fit_hint",
    ],
    "04_CONTRACTS": [
        "contract_id",
        "customer_id",
        "status",
        "description",
        "payment_terms",
    ],
    "05_PRODUCTS": [
        "service_id",
        "service_name",
        "pricing_model",
        "target_segment",
    ],
    "06_ORDERS": [
        "order_id",
        "contract_id",
        "customer_id",
        "status",
        "service_id",
        "delivery_note",
    ],
    "07_INVOICES": [
        "invoice_id",
        "order_id",
        "customer_id",
        "status",
    ],
    "08_BANK_TXN": [
        "txn_id",
        "bank",
        "account_id",
        "direction",
        "description",
        "counterparty_id",
        "txn_status",
    ],
    "09_CASHFLOW": [
        "month",
        "management_note",
    ],
    "10_CREDIT_PROFILE": [
        "credit_case_id",
        "company_id",
        "request_type",
        "tenor",
        "collateral_or_basis",
        "precheck_note",
        "approval_status",
    ],
    "11_BANK_PRODUCTS": [
        "bank_product_id",
        "bank",
        "product_name",
        "target_segment",
        "description",
        "automation_level",
        "fit_note",
    ],
    "12_API_CATALOG": [
        "api_id",
        "provider",
        "method",
        "endpoint",
        "description",
        "required_fields",
        "payload_example",
        "recommended_core_role",
        "catalog_status",
        "extension_rule",
    ],
    "13_RISK_RULES": [
        "rule_id",
        "risk_type",
        "trigger_condition",
        "severity",
        "required_action",
        "owner_agent",
    ],
    "14_ALERTS": [
        "alert_id",
        "alert_type",
        "related_record",
        "severity",
        "description",
        "recommended_action",
    ],
    "15_AGENT_TASKS": [
        "task_id",
        "core_role",
        "suggested_agent_or_skill",
        "task_description",
        "minimum_baseline_inputs",
        "allowed_extended_inputs",
        "expected_handoff_output",
        "round_usage",
    ],
    "16_PUBLIC_TESTS": [
        "test_id",
        "test_name",
        "input_condition",
        "expected_output",
        "round_usage",
    ],
    "17_CRISIS_CARD_TEMPLATE": [
        "crisis_card_id",
        "trigger_event",
        "data_change",
        "expected_agent_response",
        "decision_update_required",
    ],
    "19_DATA_DICTIONARY": [
        "table_name",
        "column_name",
        "business_meaning",
        "example_value",
        "used_by_agent",
    ],
    "20_DATA_CLASS": [
        "field_name",
        "data_class",
        "masking_required",
        "masking_rule",
        "external_sharing_allowed",
    ],
    "21_MASKING_EXAMPLES": [
        "field_name",
        "raw_value",
        "masked_value",
        "use_case",
    ],
    "22_API_HANDLING_RULES": [
        "rule_id",
        "api_context",
        "required_check",
        "fallback_if_failed",
    ],
    "23_DESIGN_LOG": [
        "log_id",
        "design_decision",
        "rationale",
        "status",
    ],
    "24_AI_USE_DISCLOSURE": [
        "tool_or_service",
        "usage_purpose",
        "human_verification",
        "evidence_note",
    ],
    "25_RUNTIME_LOG_SCHEMA": [
        "field_name",
        "description",
        "example_value",
    ],
    "26_API_ASSUMPTIONS": [
        "assumption_id",
        "assumption",
        "implication",
        "mitigation",
    ],
}


# =========================
# 2. HELPER SQL
# =========================

def full_table_name(table_name: str) -> str:
    """
    Trả về tên bảng đầy đủ dạng main."TABLE_NAME".
    """
    return f"{quote_identifier(DEFAULT_SCHEMA)}.{quote_identifier(table_name)}"


def table_exists(conn, table_name: str) -> bool:
    """
    Kiểm tra bảng có tồn tại trong schema main không.
    """
    result = conn.sql(
        f"""
        SELECT COUNT(*) AS cnt
        FROM information_schema.tables
        WHERE table_schema = '{DEFAULT_SCHEMA}'
          AND table_type = 'BASE TABLE'
          AND table_name = '{table_name}'
        """
    ).fetchone()[0]

    return result > 0


def get_existing_columns(conn, table_name: str) -> List[str]:
    """
    Lấy danh sách cột hiện có trong bảng để tránh lỗi nếu thiếu cột.
    """
    result = conn.sql(f"DESCRIBE {full_table_name(table_name)}").fetchdf()
    return result["column_name"].tolist()


# =========================
# 3. INLINE CLEANING EXPRESSIONS
# Không tạo macro trong MotherDuck.
# =========================

def clean_excel_date_expr(column_name: str) -> str:
    """
    Công thức inline để đổi Excel serial date/text date sang DATE.
    Không tạo macro trong MotherDuck.
    """
    col = quote_identifier(column_name)

    return f"""
    CASE
        WHEN {col} IS NULL THEN NULL

        WHEN TRY_CAST(CAST({col} AS VARCHAR) AS DOUBLE) IS NOT NULL
             AND TRY_CAST(CAST({col} AS VARCHAR) AS DOUBLE) BETWEEN 20000 AND 60000
        THEN DATE '1899-12-30'
             + CAST(ROUND(TRY_CAST(CAST({col} AS VARCHAR) AS DOUBLE)) AS INTEGER)

        WHEN TRY_CAST(CAST({col} AS VARCHAR) AS TIMESTAMP) IS NOT NULL
        THEN CAST(TRY_CAST(CAST({col} AS VARCHAR) AS TIMESTAMP) AS DATE)

        ELSE NULL
    END
    """


def clean_number_expr(column_name: str) -> str:
    """
    Công thức inline để làm sạch tiền/số/rate/score trước khi ép kiểu.
    Không tạo macro trong MotherDuck.
    """
    col = quote_identifier(column_name)

    return f"""
    TRY_CAST(
        NULLIF(
            regexp_replace(TRIM(CAST({col} AS VARCHAR)), '[^0-9.-]', '', 'g'),
            ''
        ) AS DOUBLE
    )
    """


def clean_text_expr(column_name: str) -> str:
    """
    Công thức inline để trim text.
    Chuỗi rỗng sau khi trim sẽ thành NULL.
    """
    col = quote_identifier(column_name)
    return f"NULLIF(TRIM(CAST({col} AS VARCHAR)), '')"


# =========================
# 4. CHUẨN HÓA DATE
# =========================

def normalize_date_columns(conn) -> None:
    """
    Chuẩn hóa các cột ngày sang DATE.
    """
    print("\nSTEP 1 - Normalize DATE columns")

    for table_name, columns in DATE_COLUMNS.items():
        if not table_exists(conn, table_name):
            print(f"Skip missing table: {table_name}")
            continue

        existing_columns = get_existing_columns(conn, table_name)

        for column_name in columns:
            if column_name not in existing_columns:
                print(f"Skip missing column: {table_name}.{column_name}")
                continue

            print(f"DATE   {table_name}.{column_name}")

            conn.sql(
                f"""
                ALTER TABLE {full_table_name(table_name)}
                ALTER COLUMN {quote_identifier(column_name)}
                SET DATA TYPE DATE
                USING ({clean_excel_date_expr(column_name)})
                """
            )


# =========================
# 5. CHUẨN HÓA MONEY
# =========================

def normalize_money_columns(conn) -> None:
    """
    Chuẩn hóa các cột tiền VND sang DECIMAL(18,0).
    """
    print("\nSTEP 2 - Normalize MONEY columns")

    for table_name, columns in MONEY_COLUMNS.items():
        if not table_exists(conn, table_name):
            print(f"Skip missing table: {table_name}")
            continue

        existing_columns = get_existing_columns(conn, table_name)

        for column_name in columns:
            if column_name not in existing_columns:
                print(f"Skip missing column: {table_name}.{column_name}")
                continue

            print(f"DECIMAL(18,0) {table_name}.{column_name}")

            conn.sql(
                f"""
                ALTER TABLE {full_table_name(table_name)}
                ALTER COLUMN {quote_identifier(column_name)}
                SET DATA TYPE DECIMAL(18,0)
                USING ({clean_number_expr(column_name)})
                """
            )


# =========================
# 6. CHUẨN HÓA RATIO
# =========================

def normalize_ratio_columns(conn) -> None:
    """
    Chuẩn hóa các cột tỷ lệ/margin/reliability/eligibility sang DECIMAL(5,4).
    """
    print("\nSTEP 3 - Normalize RATIO columns")

    for table_name, columns in RATIO_COLUMNS.items():
        if not table_exists(conn, table_name):
            print(f"Skip missing table: {table_name}")
            continue

        existing_columns = get_existing_columns(conn, table_name)

        for column_name in columns:
            if column_name not in existing_columns:
                print(f"Skip missing column: {table_name}.{column_name}")
                continue

            print(f"DECIMAL(5,4)  {table_name}.{column_name}")

            conn.sql(
                f"""
                ALTER TABLE {full_table_name(table_name)}
                ALTER COLUMN {quote_identifier(column_name)}
                SET DATA TYPE DECIMAL(5,4)
                USING ({clean_number_expr(column_name)})
                """
            )


# =========================
# 7. CHUẨN HÓA RISK SCORE
# =========================

def normalize_risk_score_columns(conn) -> None:
    """
    Chuẩn hóa các cột risk score sang DECIMAL(5,2).
    """
    print("\nSTEP 4 - Normalize RISK SCORE columns")

    for table_name, columns in RISK_SCORE_COLUMNS.items():
        if not table_exists(conn, table_name):
            print(f"Skip missing table: {table_name}")
            continue

        existing_columns = get_existing_columns(conn, table_name)

        for column_name in columns:
            if column_name not in existing_columns:
                print(f"Skip missing column: {table_name}.{column_name}")
                continue

            print(f"DECIMAL(5,2)  {table_name}.{column_name}")

            conn.sql(
                f"""
                ALTER TABLE {full_table_name(table_name)}
                ALTER COLUMN {quote_identifier(column_name)}
                SET DATA TYPE DECIMAL(5,2)
                USING ({clean_number_expr(column_name)})
                """
            )


# =========================
# 8. TRIM TEXT
# =========================

def normalize_text_columns(conn) -> None:
    """
    Trim khoảng trắng cho các cột text.
    Không đổi hoa/thường.
    Không map lại enum.
    """
    print("\nSTEP 5 - Normalize TEXT columns")

    for table_name, columns in TEXT_COLUMNS.items():
        if not table_exists(conn, table_name):
            print(f"Skip missing table: {table_name}")
            continue

        existing_columns = get_existing_columns(conn, table_name)
        valid_columns = [col for col in columns if col in existing_columns]

        if not valid_columns:
            continue

        assignments = [
            f"{quote_identifier(col)} = {clean_text_expr(col)}"
            for col in valid_columns
        ]

        print(f"TEXT   {table_name}: {len(valid_columns)} columns")

        conn.sql(
            f"""
            UPDATE {full_table_name(table_name)}
            SET {", ".join(assignments)}
            """
        )


# =========================
# 9. KIỂM TRA SAU CHUẨN HÓA
# =========================

def verify_normalization(conn) -> None:
    """
    In schema một số bảng quan trọng để kiểm tra kiểu dữ liệu sau chuẩn hóa.
    """
    print("\nSTEP 6 - Verify important table schemas")

    tables_to_check = [
        "03_CUSTOMERS",
        "04_CONTRACTS",
        "05_PRODUCTS",
        "06_ORDERS",
        "07_INVOICES",
        "08_BANK_TXN",
        "09_CASHFLOW",
        "10_CREDIT_PROFILE",
        "11_BANK_PRODUCTS",
        "14_ALERTS",
    ]

    for table_name in tables_to_check:
        if not table_exists(conn, table_name):
            continue

        print(f"\nSchema: {table_name}")
        schema_df = conn.sql(f"DESCRIBE {full_table_name(table_name)}").fetchdf()
        print(schema_df[["column_name", "column_type"]])


# =========================
# 10. MAIN FLOW
# =========================

def main() -> None:
    uploader = MotherDuckExcelUploader()

    try:
        conn = uploader.connect()

        normalize_date_columns(conn)
        normalize_money_columns(conn)
        normalize_ratio_columns(conn)
        normalize_risk_score_columns(conn)
        normalize_text_columns(conn)
        verify_normalization(conn)

        print("\nData normalization completed successfully.")

    finally:
        uploader.close()


if __name__ == "__main__":
    main()