from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv


def query_neo4j(
    statement: str,
    parameters: dict[str, Any] | None = None,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run a compact read query against Neo4j Aura Query API.

    The app treats Neo4j as a knowledge-graph router/context source. Runtime
    business rows still come from MotherDuck, so this client deliberately
    returns a small, JSON-safe result for agent prompts and UI evidence.
    """
    load_dotenv(override=True)
    config = _config()
    if not config["enabled"]:
        return {
            "enabled": False,
            "status": "disabled",
            "friendly_error": config["friendly_error"],
            "records": [],
            "record_count": 0,
        }

    max_rows = limit or config["limit"]
    try:
        with httpx.Client(timeout=config["timeout"], verify=config["verify_ssl"]) as client:
            response = client.post(
                config["query_url"],
                auth=(config["username"], config["password"]),
                json={
                    "statement": _with_limit(statement, max_rows),
                    "parameters": parameters or {},
                },
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        return {
            "enabled": True,
            "status": "error",
            "friendly_error": _friendly_error(exc),
            "records": [],
            "record_count": 0,
        }

    records = _records_from_response(payload, max_rows)
    return {
        "enabled": True,
        "status": "ok",
        "query_url_host": urlparse(config["query_url"]).netloc,
        "database": config["database"],
        "records": records,
        "record_count": len(records),
    }


def _config() -> dict[str, Any]:
    uri = os.getenv("NEO4J_URI", "").strip()
    username = os.getenv("NEO4J_USERNAME", "").strip()
    password = os.getenv("NEO4J_PASSWORD", "").strip()
    database = os.getenv("NEO4J_DATABASE", "").strip()
    query_url = os.getenv("NEO4J_QUERY_URL", "").strip()
    limit = int(os.getenv("NEO4J_QUERY_LIMIT", "8") or 8)
    timeout = float(os.getenv("NEO4J_TIMEOUT_SECONDS", "8") or 8)
    verify_ssl = os.getenv("NEO4J_SSL_VERIFY", "true").strip().lower() not in {
        "0",
        "false",
        "no",
    }

    missing = [
        key
        for key, value in {
            "NEO4J_URI": uri,
            "NEO4J_USERNAME": username,
            "NEO4J_PASSWORD": password,
            "NEO4J_DATABASE": database,
        }.items()
        if not value
    ]
    if missing:
        return {
            "enabled": False,
            "friendly_error": "Missing " + ", ".join(missing),
        }

    if not query_url:
        host = urlparse(uri.replace("neo4j+s://", "https://", 1)).netloc
        query_url = f"https://{host}/db/{database}/query/v2"

    return {
        "enabled": True,
        "uri": uri,
        "username": username,
        "password": password,
        "database": database,
        "query_url": query_url,
        "limit": max(1, min(limit, 25)),
        "timeout": timeout,
        "verify_ssl": verify_ssl,
    }


def _with_limit(statement: str, limit: int) -> str:
    stripped = statement.strip().rstrip(";")
    if " limit " in f" {stripped.lower()} ":
        return stripped
    return f"{stripped} LIMIT {limit}"


def _records_from_response(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    data = payload.get("data") or {}
    fields = data.get("fields") or []
    values = data.get("values") or []
    if fields and isinstance(values, list):
        return [
            {
                str(field): _json_safe(value)
                for field, value in zip(fields, row)
            }
            for row in values[:limit]
            if isinstance(row, list)
        ]

    records = payload.get("records") or payload.get("results") or []
    if isinstance(records, list):
        return [_json_safe(item) for item in records[:limit]]
    return []


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        if "elementId" in value and "properties" in value:
            return {
                "labels": value.get("labels") or value.get("type"),
                "properties": _json_safe(value.get("properties", {})),
            }
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value[:8]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in {401, 403}:
            return "Neo4j authentication/permission failed. Check username, password, and database."
        if status == 404:
            return "Neo4j Query API endpoint/database was not found."
        return f"Neo4j Query API returned HTTP {status}."
    if isinstance(exc, httpx.ConnectError):
        return "Cannot connect to Neo4j Aura right now. Check network/VPN/firewall."
    if isinstance(exc, httpx.TimeoutException):
        return "Neo4j query timed out."
    return f"Neo4j query failed: {exc}"
