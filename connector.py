from __future__ import annotations

import os
from threading import RLock
from pathlib import Path
from typing import List

import duckdb
import pandas as pd
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
DATA_DIR = BASE_DIR / "data"
EXCEL_PATH = DATA_DIR / "MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx"
DEFAULT_SCHEMA = "main"


def quote_identifier(identifier: str) -> str:
    """
    Quote SQL identifiers safely for DuckDB/MotherDuck.

    Needed because:
    - Database name may contain spaces, e.g. OPC Database
    - Sheet names start with numbers, e.g. 04_CONTRACTS
    """
    return '"' + identifier.replace('"', '""') + '"'


class MotherDuckExcelUploader:
    """
    Handles MotherDuck connection and Excel sheet upload.
    """

    def __init__(self, excel_path: Path = EXCEL_PATH):
        load_dotenv(ENV_PATH)

        self.token = os.getenv("MOTHERDUCK_TOKEN")
        self.database_name = os.getenv("MOTHERDUCK_DATABASE", "OPC Database")
        self.excel_path = excel_path
        self.connection: duckdb.DuckDBPyConnection | None = None
        self._lock = RLock()

        if not self.token:
            raise ValueError(
                "Missing MOTHERDUCK_TOKEN in .env. "
                "Please add MOTHERDUCK_TOKEN before running this script."
            )

        if not self.database_name:
            raise ValueError(
                "Missing MOTHERDUCK_DATABASE in .env. "
                "Please add MOTHERDUCK_DATABASE before running this script."
            )

        os.environ["motherduck_token"] = self.token

    def connect(self) -> duckdb.DuckDBPyConnection:
        """
        Connect to MotherDuck and select the target database.
        If the database does not exist, create it.
        """
        with self._lock:
            if self.connection is None:
                print("Connecting to MotherDuck...")

                self.connection = duckdb.connect("md:")

                self.connection.sql(
                    f"CREATE DATABASE IF NOT EXISTS {quote_identifier(self.database_name)}"
                )

                self.connection.sql(
                    f"USE {quote_identifier(self.database_name)}"
                )

                print(f"Connected to database: {self.database_name}")

            return self.connection

    def close(self) -> None:
        """
        Close the MotherDuck connection.
        """
        with self._lock:
            if self.connection is not None:
                self.connection.close()
                self.connection = None
                print("Connection closed.")

    def list_tables(self) -> List[str]:
        """
        Return all base tables in schema main.
        """
        with self._lock:
            conn = self.connect()

            tables_df = conn.sql(
                f"""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = '{DEFAULT_SCHEMA}'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            ).fetchdf()

            return tables_df["table_name"].tolist()

    def describe_table(self, table_name: str) -> pd.DataFrame:
        """
        Return column metadata for a table in schema main.
        """
        with self._lock:
            conn = self.connect()

            return conn.sql(
                f"DESCRIBE {quote_identifier(DEFAULT_SCHEMA)}.{quote_identifier(table_name)}"
            ).fetchdf()

    def read_table(self, table_name: str, limit: int = 100) -> pd.DataFrame:
        """
        Return rows from a table, capped at 10,000 rows for the web/API viewer.
        """
        with self._lock:
            conn = self.connect()
            safe_limit = max(1, min(int(limit), 10_000))

            return conn.sql(
                f"""
                SELECT *
                FROM {quote_identifier(DEFAULT_SCHEMA)}.{quote_identifier(table_name)}
                LIMIT {safe_limit}
                """
            ).fetchdf()

    def execute_query(self, sql_query: str) -> pd.DataFrame:
        """
        Execute a SQL query and return the result as a DataFrame.
        """
        with self._lock:
            conn = self.connect()
            return conn.sql(sql_query).fetchdf()

    def drop_all_tables_in_main(self) -> None:
        """
        Drop all existing tables in schema main.
        This does not drop the database.
        """
        conn = self.connect()
        table_names = self.list_tables()

        if not table_names:
            print("No existing tables found in schema main.")
            return

        print(f"Found {len(table_names)} existing tables in schema main.")
        print("Dropping old tables...")

        for table_name in table_names:
            print(f"  DROP TABLE {table_name}")
            conn.sql(
                f"DROP TABLE IF EXISTS {quote_identifier(DEFAULT_SCHEMA)}.{quote_identifier(table_name)}"
            )

        print("All old tables dropped.")

    def get_excel_sheet_names(self) -> List[str]:
        """
        Read and return all sheet names from the Excel file.
        """
        if not self.excel_path.exists():
            raise FileNotFoundError(
                f"Excel file not found:\n{self.excel_path}\n\n"
                "Please put the Excel file inside the data folder."
            )

        excel_file = pd.ExcelFile(self.excel_path)
        return excel_file.sheet_names

    def upload_sheet(self, sheet_name: str, index: int) -> None:
        """
        Upload one Excel sheet as one MotherDuck table.
        Table name = sheet name.
        """
        conn = self.connect()

        df = pd.read_excel(
            self.excel_path,
            sheet_name=sheet_name,
            dtype=object,
        )

        # Preserve raw data. Only convert pandas NaN to database NULL.
        df = df.where(pd.notnull(df), None)

        temp_view_name = f"_temp_upload_view_{index}"

        try:
            conn.register(temp_view_name, df)

            conn.sql(
                f"""
                CREATE TABLE {quote_identifier(DEFAULT_SCHEMA)}.{quote_identifier(sheet_name)} AS
                SELECT *
                FROM {quote_identifier(temp_view_name)}
                """
            )

            row_count = conn.sql(
                f"""
                SELECT COUNT(*) AS row_count
                FROM {quote_identifier(DEFAULT_SCHEMA)}.{quote_identifier(sheet_name)}
                """
            ).fetchone()[0]

            column_count = len(df.columns)

            print(f"Uploaded {sheet_name}: {row_count} rows, {column_count} columns")

        finally:
            try:
                conn.unregister(temp_view_name)
            except Exception:
                pass

    def upload_all_sheets(self) -> None:
        """
        Upload all sheets from the Excel file to MotherDuck.
        """
        sheet_names = self.get_excel_sheet_names()

        print(f"Excel file: {self.excel_path}")
        print(f"Found {len(sheet_names)} sheets:")
        for sheet_name in sheet_names:
            print(f"  - {sheet_name}")

        print("Uploading sheets...")

        for index, sheet_name in enumerate(sheet_names, start=1):
            print(f"[{index}/{len(sheet_names)}] Uploading {sheet_name}")
            self.upload_sheet(sheet_name=sheet_name, index=index)

        print("All sheets uploaded successfully.")

    def reload_from_excel(self) -> None:
        """
        Main flow:
        1. Connect to MotherDuck
        2. Drop old tables in schema main
        3. Upload all sheets from Excel
        4. Print final table list
        """
        self.connect()

        print("\nSTEP 1 - Drop old tables")
        self.drop_all_tables_in_main()

        print("\nSTEP 2 - Upload Excel sheets")
        self.upload_all_sheets()

        print("\nSTEP 3 - Verify uploaded tables")
        tables = self.list_tables()

        print(f"Total tables after upload: {len(tables)}")
        for table_name in tables:
            print(f"  - {table_name}")


def main() -> None:
    uploader = MotherDuckExcelUploader()

    try:
        uploader.reload_from_excel()
    finally:
        uploader.close()


if __name__ == "__main__":
    main()


_connector: MotherDuckExcelUploader | None = None


def get_connector() -> MotherDuckExcelUploader:
    """
    Return the shared MotherDuck connector instance used by the web app/tools.
    """
    global _connector

    if _connector is None:
        _connector = MotherDuckExcelUploader()

    return _connector
