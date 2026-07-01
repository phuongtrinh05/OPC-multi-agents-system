"""
MotherDuck Connection Manager
=============================
Singleton connection manager for MotherDuck (DuckDB cloud) database.
Provides helper methods to read tables, list tables, describe schemas,
and execute queries.
"""

import os
import duckdb
import pandas as pd
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class MotherDuckConnector:
    """Singleton connection manager for MotherDuck database."""

    _instance = None
    _connection = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._connection is None:
            self._connect()

    def _connect(self):
        """Establish connection to MotherDuck."""
        token = os.getenv("MOTHERDUCK_TOKEN")
        self._db_name = os.getenv("MOTHERDUCK_DATABASE", "OPC Database")

        if not token:
            raise ValueError(
                "MOTHERDUCK_TOKEN is not set. "
                "Please add it to your .env file."
            )

        os.environ["motherduck_token"] = token

        try:
            # Connect to MotherDuck without specifying db in connection string
            # then USE the database explicitly for reliability
            self._connection = duckdb.connect("md:")
            self._connection.sql(f'USE "{self._db_name}"')
            print(f"✅ Connected to MotherDuck database: {self._db_name}")
        except Exception as e:
            self._connection = None
            raise ConnectionError(f"Failed to connect to MotherDuck: {e}")

    @property
    def connection(self):
        """Get the active DuckDB connection, reconnecting if needed."""
        if self._connection is None:
            self._connect()
        # Test connection is still alive
        try:
            self._connection.sql("SELECT 1")
        except Exception:
            print("⚠️ Connection lost, reconnecting...")
            self._connection = None
            self._connect()
        return self._connection

    def list_tables(self) -> list[str]:
        """List all tables in the database.

        Returns:
            List of table names.
        """
        try:
            result = self.connection.sql(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main' AND table_type = 'BASE TABLE' "
                "ORDER BY table_name"
            ).fetchdf()
            return result["table_name"].tolist()
        except Exception:
            # Fallback to SHOW TABLES if information_schema doesn't work
            result = self.connection.sql("SHOW TABLES").fetchdf()
            col = result.columns[0]  # Use first column regardless of name
            return result[col].tolist()

    def describe_table(self, table_name: str) -> pd.DataFrame:
        """Describe the schema of a table (columns, types, nullable).

        Args:
            table_name: Name of the table to describe.

        Returns:
            DataFrame with column_name, column_type, null info.
        """
        # Sanitize table name to prevent SQL injection
        safe_name = table_name.replace('"', '""')
        result = self.connection.sql(f'DESCRIBE "{safe_name}"').fetchdf()
        return result

    def read_table(self, table_name: str, limit: int = 100) -> pd.DataFrame:
        """Read data from a table with an optional row limit.

        Args:
            table_name: Name of the table to read.
            limit: Maximum number of rows to return (default 100).

        Returns:
            DataFrame with the table data.
        """
        safe_name = table_name.replace('"', '""')
        limit = min(max(1, limit), 10000)  # Clamp between 1 and 10000
        result = self.connection.sql(
            f'SELECT * FROM "{safe_name}" LIMIT {limit}'
        ).fetchdf()
        return result

    def execute_query(self, sql: str) -> pd.DataFrame:
        """Execute a SQL query and return results as DataFrame.

        Args:
            sql: The SQL query to execute.

        Returns:
            DataFrame with query results.
        """
        result = self.connection.sql(sql).fetchdf()
        return result

    def execute_write(self, sql: str) -> str:
        """Execute a write SQL statement (INSERT, UPDATE).

        Args:
            sql: The SQL statement to execute.

        Returns:
            Success message with affected rows info.
        """
        self.connection.sql(sql)
        return "Query executed successfully."

    def close(self):
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            MotherDuckConnector._instance = None
            print("🔌 Connection closed.")


def get_connector() -> MotherDuckConnector:
    """Get or create the singleton MotherDuckConnector instance.

    Returns:
        The MotherDuckConnector singleton instance.
    """
    return MotherDuckConnector()


# Quick test when run directly
if __name__ == "__main__":
    conn = get_connector()
    print("\n📋 Tables:", conn.list_tables())
    conn.close()