"""
LangChain Tool Functions
========================
CRUD tools for MotherDuck database operations + data masking utility.
All tools are decorated with @tool for LangGraph agent integration.
"""

import re
import hashlib
import json
import pandas as pd
from langchain_core.tools import tool
from connector import get_connector


# =============================================================================
# Data Masking Utilities
# =============================================================================
# Masking rules based on the masking_examples table in OPC Database:
#
# | source_field     | raw_example  | masked_example | rule               |
# |------------------|------------- |----------------|--------------------|
# | customer_id      | CUS-005      | CUS-***005     | Keep prefix, mask  |
# | account_id       | OPC_MAIN     | OPC_****       | Keep prefix, mask  |
# | company_name     | OPC Digital  | OPC D*****     | Partial mask       |
# | contract_value   | 4.2E+09      | 4.2B band      | Aggregate to band  |
# | access_token     | eyJ...mock   | [SECRET]       | Full redact        |

# Column name patterns -> mask type
SENSITIVE_PATTERNS = {
    # ID fields: customer_id, user_id, employee_id, etc.
    "id_code": r"(?i)(customer_id|user_id|employee_id|client_id|member_id|order_id)",
    # Account/internal codes: account_id, account_number, etc.
    "account_code": r"(?i)(account_id|account_number|account_code|acc_id)",
    # Company/org names
    "company_name": r"(?i)(company_name|company|org_name|organization|business_name)",
    # Financial values: contract_value, salary, revenue, amount, etc.
    "financial": r"(?i)(contract_value|salary|income|revenue|amount|price|cost|total|value|budget|payment)",
    # Tokens/secrets: access_token, api_key, password, secret, etc.
    "secret": r"(?i)(access_token|api_key|token|password|secret|credential|private_key|auth)",
    # Email
    "email": r"(?i)(email|e_mail|mail_address)",
    # Phone
    "phone": r"(?i)(phone|tel|mobile|contact_number|fax)",
    # Person name
    "person_name": r"(?i)(first_name|last_name|full_name|customer_name|person_name|employee_name|contact_name)",
    # Address
    "address": r"(?i)(address|street|city|zip|postal|ward|district)",
    # Generic ID (catch-all for _id columns)
    "generic_id": r"(?i)^.*_id$",
}


def _mask_id_code(value: str) -> str:
    """Mask ID codes: CUS-005 -> CUS-***005 (keep prefix + last 3 digits)."""
    value = str(value)
    match = re.match(r"^([A-Za-z]+[-_]?)", value)
    if match:
        prefix = match.group(1)
        rest = value[len(prefix):]
        if len(rest) >= 3:
            return f"{prefix}***{rest[-3:]}"
        return f"{prefix}***{rest}"
    if len(value) > 6:
        return value[:3] + "***" + value[-3:]
    return value[:2] + "***"


def _mask_account_code(value: str) -> str:
    """Mask account codes: OPC_MAIN -> OPC_**** (keep prefix, mask rest)."""
    value = str(value)
    match = re.match(r"^([A-Za-z]+[-_]?)", value)
    if match:
        prefix = match.group(1)
        rest_len = len(value) - len(prefix)
        return prefix + "*" * max(rest_len, 4)
    if len(value) > 3:
        return value[:3] + "*" * (len(value) - 3)
    return "****"


def _mask_company_name(value: str) -> str:
    """Mask company names: OPC Digital -> OPC D***** (keep first word + first char)."""
    if not isinstance(value, str):
        return "***"
    parts = value.split()
    if len(parts) == 0:
        return "***"
    if len(parts) == 1:
        if len(value) > 3:
            return value[:3] + "*" * (len(value) - 3)
        return value
    first_word = parts[0]
    rest = value[len(first_word) + 1:]
    if len(rest) > 1:
        masked_rest = rest[0] + "*" * (len(rest) - 1)
    else:
        masked_rest = "***"
    return f"{first_word} {masked_rest}"


def _mask_financial(value) -> str:
    """Mask financial values: 4200000000 -> 4.2B band (aggregate to band)."""
    try:
        num = float(value)
    except (ValueError, TypeError):
        return str(value)

    abs_num = abs(num)
    if abs_num >= 1_000_000_000:
        return f"{num / 1_000_000_000:.1f}B band"
    elif abs_num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M band"
    elif abs_num >= 1_000:
        return f"{num / 1_000:.1f}K band"
    else:
        return f"{num:.0f} band"


def _mask_secret(value: str) -> str:
    """Mask tokens/secrets: eyJ...mock -> [SECRET]."""
    return "[SECRET]"


def _mask_email(value: str) -> str:
    """Mask email: nguyenvana@gmail.com -> ngu***@***.com."""
    if not isinstance(value, str) or "@" not in value:
        return "***"
    local, domain = value.rsplit("@", 1)
    domain_parts = domain.rsplit(".", 1)
    masked_local = local[:3] + "***" if len(local) > 3 else "***"
    masked_domain = "***." + domain_parts[-1] if len(domain_parts) > 1 else "***"
    return f"{masked_local}@{masked_domain}"


def _mask_phone(value: str) -> str:
    """Mask phone: 0912345678 -> ***5678."""
    if not isinstance(value, str):
        return "***"
    digits = re.sub(r"\D", "", str(value))
    if len(digits) >= 4:
        return "***" + digits[-4:]
    return "***"


def _mask_person_name(value: str) -> str:
    """Mask person names: Nguyen Van An -> Nguyen V*** A***."""
    if not isinstance(value, str):
        return "***"
    parts = value.split()
    if len(parts) <= 1:
        return value[0] + "***" if value else "***"
    masked = [parts[0]] + [p[0] + "***" for p in parts[1:] if p]
    return " ".join(masked)


def _mask_address(value: str) -> str:
    """Mask address: 123 Le Loi, Q1 -> 12***."""
    value = str(value)
    if len(value) <= 4:
        return "***"
    return value[:2] + "***"


def _mask_generic_id(value: str) -> str:
    """Mask generic IDs: keep first chars, mask rest."""
    value = str(value)
    if len(value) <= 3:
        return "***"
    return value[:2] + "***" + value[-2:]


def _detect_mask_type(column_name: str) -> str | None:
    """Detect which mask type to apply based on column name.

    Args:
        column_name: The column name to check.

    Returns:
        The mask type string or None if no match.
    """
    for mask_type, pattern in SENSITIVE_PATTERNS.items():
        if re.search(pattern, column_name):
            return mask_type
    return None


MASK_FUNCTIONS = {
    "id_code": _mask_id_code,
    "account_code": _mask_account_code,
    "company_name": _mask_company_name,
    "financial": _mask_financial,
    "secret": _mask_secret,
    "email": _mask_email,
    "phone": _mask_phone,
    "person_name": _mask_person_name,
    "address": _mask_address,
    "generic_id": _mask_generic_id,
}


def mask_sensitive_data(
    df: pd.DataFrame,
    columns_to_mask: list[str] | None = None,
    auto_detect: bool = True,
) -> pd.DataFrame:
    """Mask sensitive data in a DataFrame before sending to LLM.

    This function detects and masks personally identifiable information (PII)
    such as emails, phone numbers, names, addresses, and financial data.

    Args:
        df: The DataFrame containing data to mask.
        columns_to_mask: Explicit list of column names to mask.
            If None and auto_detect=True, columns are detected automatically.
        auto_detect: If True, automatically detect sensitive columns
            based on column name patterns.

    Returns:
        A new DataFrame with sensitive data masked.
    """
    masked_df = df.copy()

    # Determine columns to mask
    mask_map: dict[str, str] = {}  # column_name -> mask_type

    if columns_to_mask:
        for col in columns_to_mask:
            if col in masked_df.columns:
                detected = _detect_mask_type(col)
                mask_map[col] = detected if detected else "name"

    if auto_detect:
        for col in masked_df.columns:
            if col not in mask_map:
                detected = _detect_mask_type(col)
                if detected:
                    mask_map[col] = detected

    # Apply masking
    for col, mask_type in mask_map.items():
        mask_fn = MASK_FUNCTIONS.get(mask_type, _mask_generic_id)
        masked_df[col] = masked_df[col].apply(
            lambda x: mask_fn(x) if pd.notna(x) else x
        )

    return masked_df


# =============================================================================
# LangChain Tools for Agent
# =============================================================================


@tool
def list_tables_tool() -> str:
    """List all available tables in the MotherDuck OPC Database.

    Use this tool to discover what tables exist in the database.
    Returns a list of table names.
    """
    try:
        conn = get_connector()
        tables = conn.list_tables()
        return f"Available tables ({len(tables)}):\n" + "\n".join(
            f"  - {t}" for t in tables
        )
    except Exception as e:
        return f"Error listing tables: {e}"


@tool
def describe_table_tool(table_name: str) -> str:
    """Describe the schema (columns, data types) of a specific table.

    Use this tool to understand the structure of a table before querying it.

    Args:
        table_name: The name of the table to describe.
    """
    try:
        conn = get_connector()
        schema_df = conn.describe_table(table_name)
        result = f"Schema for table '{table_name}':\n"
        result += schema_df.to_string(index=False)
        return result
    except Exception as e:
        return f"Error describing table '{table_name}': {e}"


@tool
def read_table_tool(table_name: str, limit: int = 20) -> str:
    """Read data from a table in the database.

    Use this tool to view the contents of a table. Data with sensitive
    columns (email, phone, name, etc.) will be automatically masked.

    Args:
        table_name: The name of the table to read.
        limit: Maximum number of rows to return (default 20, max 10000).
    """
    try:
        conn = get_connector()
        df = conn.read_table(table_name, limit)

        # Apply data masking for sensitive columns
        masked_df = mask_sensitive_data(df)

        result = f"Table '{table_name}' ({len(masked_df)} rows):\n"
        result += masked_df.to_string(index=False)
        return result
    except Exception as e:
        return f"Error reading table '{table_name}': {e}"


@tool
def execute_sql_tool(sql_query: str) -> str:
    """Execute a read-only SQL SELECT query on the database.

    Use this tool to run custom SQL queries. Only SELECT statements are allowed.
    Results with sensitive columns will be automatically masked.

    Args:
        sql_query: The SQL SELECT query to execute.
    """
    # Block non-SELECT queries for safety
    normalized = sql_query.strip().upper()
    if not normalized.startswith("SELECT"):
        return (
            "Error: Only SELECT queries are allowed with this tool. "
            "Use insert_data_tool or update_data_tool for write operations."
        )

    try:
        conn = get_connector()
        df = conn.execute_query(sql_query)

        # Apply data masking
        masked_df = mask_sensitive_data(df)

        result = f"Query results ({len(masked_df)} rows):\n"
        result += masked_df.to_string(index=False)
        return result
    except Exception as e:
        return f"Error executing query: {e}"


@tool
def insert_data_tool(table_name: str, data: str) -> str:
    """Insert new data into a table.

    Use this tool to add new records to a table. Provide data as a JSON
    string with column names as keys.

    Args:
        table_name: The name of the table to insert into.
        data: JSON string of the data to insert.
              Example: '{"column1": "value1", "column2": "value2"}'
              Or a list: '[{"col1": "v1"}, {"col1": "v2"}]'
    """
    try:
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            parsed = [parsed]

        if not isinstance(parsed, list) or not all(
            isinstance(r, dict) for r in parsed
        ):
            return "Error: Data must be a JSON object or array of objects."

        conn = get_connector()
        safe_table = table_name.replace('"', '""')

        inserted = 0
        for record in parsed:
            columns = ", ".join(f'"{k}"' for k in record.keys())
            placeholders = ", ".join("?" for _ in record.values())
            sql = f'INSERT INTO "{safe_table}" ({columns}) VALUES ({placeholders})'
            conn.connection.execute(sql, list(record.values()))
            inserted += 1

        return f"Successfully inserted {inserted} row(s) into '{table_name}'."
    except json.JSONDecodeError:
        return "Error: Invalid JSON data format."
    except Exception as e:
        return f"Error inserting data into '{table_name}': {e}"


@tool
def update_data_tool(table_name: str, set_values: str, where_clause: str) -> str:
    """Update existing data in a table.

    Use this tool to modify records that match a WHERE condition.

    Args:
        table_name: The name of the table to update.
        set_values: JSON string of columns and new values.
                    Example: '{"column1": "new_value1", "column2": 42}'
        where_clause: SQL WHERE clause (without the WHERE keyword).
                      Example: 'id = 5' or 'name = \\'John\\''
    """
    try:
        parsed = json.loads(set_values)
        if not isinstance(parsed, dict):
            return "Error: set_values must be a JSON object."

        conn = get_connector()
        safe_table = table_name.replace('"', '""')

        set_parts = []
        values = []
        for k, v in parsed.items():
            set_parts.append(f'"{k}" = ?')
            values.append(v)

        set_clause = ", ".join(set_parts)
        sql = f'UPDATE "{safe_table}" SET {set_clause} WHERE {where_clause}'
        conn.connection.execute(sql, values)

        return f"Successfully updated rows in '{table_name}' where {where_clause}."
    except json.JSONDecodeError:
        return "Error: Invalid JSON format for set_values."
    except Exception as e:
        return f"Error updating '{table_name}': {e}"


# All tools list for agent registration
ALL_TOOLS = [
    list_tables_tool,
    describe_table_tool,
    read_table_tool,
    execute_sql_tool,
    insert_data_tool,
    update_data_tool,
]
