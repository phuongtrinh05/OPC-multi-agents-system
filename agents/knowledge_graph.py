from __future__ import annotations

from functools import lru_cache
from typing import Any

from agents.neo4j_client import query_neo4j


AGENT_ALIASES = {
    "Data Intake & Screening Agent": "Data & Finance Agent",
    "Finance Monitor + AI/NLP Reasoning Agent": "Data & Finance Agent",
    "AI/NLP Reasoning Tool": "Data & Finance Agent",
    "OpenAI Reasoning Agent": "Data & Finance Agent",
    "AI Reasoning Agent": "Data & Finance Agent",
}

AGENT_VIEWS = {
    "Data & Finance Agent": {
        "neo4j_agent_id": "AGENT-Finance",
        "task_id": "TASK-001",
        "min_inputs": [
            "04_CONTRACTS",
            "06_ORDERS",
            "07_INVOICES",
            "08_BANK_TXN",
            "09_CASHFLOW",
        ],
        "entities": [
            "Company",
            "Customer",
            "Contract",
            "Order",
            "BankTransaction",
            "CashFlowMonth",
            "RiskRule",
        ],
        "rule_ids": ["RR-002", "RR-003"],
        "mission": (
            "Use MotherDuck observations for contract, order, invoice, bank "
            "transaction, and cashflow data; use the Neo4j KG schema to route "
            "finance signals to downstream rules/functions."
        ),
        "handoff_output": "Cashflow summary and funding need",
    },
    "Risk & Compliance Agent": {
        "neo4j_agent_id": "AGENT-Risk",
        "task_id": "TASK-002",
        "min_inputs": [
            "08_BANK_TXN",
            "13_RISK_RULES",
            "14_ALERTS",
            "20_DATA_CLASS",
        ],
        "entities": [
            "BankTransaction",
            "RiskRule",
            "Alert",
            "HumanApproval",
            "Agent",
        ],
        "rule_ids": ["RR-001", "RR-002", "RR-003", "RR-004", "RR-005", "RR-006", "RR-007"],
        "mission": (
            "Use MotherDuck risk observations and Neo4j rule/approval schema to "
            "validate which risk flags are supported before Decision Agent runs."
        ),
        "handoff_output": "Risk flags and required approvals",
    },
    "Decision & Partner Agent": {
        "neo4j_agent_id": "AGENT-Decision",
        "task_id": "TASK-003",
        "min_inputs": [
            "10_CREDIT_PROFILE",
            "11_BANK_PRODUCTS",
            "12_API_CATALOG",
        ],
        "entities": [
            "Contract",
            "Customer",
            "CreditProfile",
            "BankProduct",
            "APIFunction",
            "HumanApproval",
            "RiskRule",
        ],
        "rule_ids": ["RR-004", "RR-005", "RR-006"],
        "mission": (
            "Use MotherDuck credit/bank/API records and Neo4j partner/approval "
            "schema to build an advisory Decision Card for Founder review."
        ),
        "handoff_output": "Decision Card with options and human confirmation points",
    },
}

SOURCE_TABLE_TO_ENTITY = {
    "04_CONTRACTS": "Contract",
    "06_ORDERS": "Order",
    "07_INVOICES": "BankTransaction",
    "08_BANK_TXN": "BankTransaction",
    "09_CASHFLOW": "CashFlowMonth",
    "10_CREDIT_PROFILE": "CreditProfile",
    "11_BANK_PRODUCTS": "BankProduct",
    "12_API_CATALOG": "APIFunction",
    "13_RISK_RULES": "RiskRule",
    "14_ALERTS": "Alert",
    "20_DATA_CLASS": "HumanApproval",
}


@lru_cache(maxsize=1)
def load_opportunity_knowledge_graph() -> dict[str, Any]:
    schema = _load_schema_from_neo4j()
    agent_nodes = _load_agent_nodes_from_neo4j()
    rule_routes = _load_rule_routes_from_neo4j()
    return {
        "graph_name": "OPC Neo4j Opportunity Knowledge Graph",
        "version": "neo4j-query-api",
        "source": {
            "type": "neo4j_query_api",
            "schema_source": "Neo4j Aura runtime graph",
            "runtime_data_source": "Neo4j for KG context/routing; MotherDuck for business rows",
            "fallback_enabled": False,
            "neo4j_status": schema.get("status"),
            "note": (
                "Knowledge graph context is queried from Neo4j through the Query API. "
                "The local importer JSON is not required for agent routing."
            ),
        },
        "entities": schema["entities"],
        "relationships": schema["relationships"],
        "agent_views": [
            _build_agent_view(agent_name, agent_nodes, rule_routes)
            for agent_name in AGENT_VIEWS
        ],
        "rule_routes": rule_routes,
        "retrieval_policy": {
            "default": (
                "Agents use Neo4j Query API results to understand allowed nodes, "
                "relationships, rules, API functions, and approval gates."
            ),
            "runtime_data": (
                "Business rows are queried from MotherDuck. Do not load duplicated "
                "node/relationship CSV data into the application runtime."
            ),
            "function_calling": (
                "Agent actions are selected from graph relationships such as "
                "TRIGGERS_RULE, CALLS_API, REQUIRES_APPROVAL, SECURED_BY, "
                "MATCHED_TO_PRODUCT, and APPLIES_FOR."
            ),
            "verification": (
                "After AI output, verify claimed rules, functions, and approval "
                "gates against the KG schema and original MotherDuck fields."
            ),
        },
    }


def compact_graph_for(agent_name: str) -> dict[str, Any]:
    graph = load_opportunity_knowledge_graph()
    view = _agent_view(graph, agent_name)
    entity_names = set(view.get("entity_access", []))
    entities = [
        item for item in graph.get("entities", [])
        if item.get("entity") in entity_names
    ]
    relationships = [
        item for item in graph.get("relationships", [])
        if item.get("from") in entity_names or item.get("to") in entity_names
    ]
    return {
        "graph_name": graph.get("graph_name"),
        "version": graph.get("version"),
        "source": graph.get("source"),
        "agent_view": {
            "agent_name": agent_name,
            "neo4j_agent_role": view.get("neo4j_agent_role"),
            "neo4j_agent_id": view.get("neo4j_agent_id"),
            "task_id": view.get("task_id"),
            "mission": view.get("mission"),
            "business_steps": view.get("business_steps", []),
            "rule_ids": view.get("rule_ids", []),
            "function_calling_policy": view.get("function_calling_policy", []),
            "output_contract": view.get("output_contract", []),
        },
        "entities": entities,
        "relationships": relationships,
        "sql_tools": view.get("function_tools", []),
        "retrieval_policy": graph.get("retrieval_policy", {}),
    }


def sql_plan_for_agent(agent_name: str, **params: Any) -> list[dict[str, Any]]:
    view = _agent_view(load_opportunity_knowledge_graph(), agent_name)
    bound = {key: value for key, value in params.items() if value is not None}
    plans = []
    for tool in view.get("function_tools", []):
        cypher = tool.get("cypher_template")
        plan = {
            "tool_name": tool.get("tool_name"),
            "purpose": tool.get("purpose"),
            "source": tool.get("source"),
            "motherduck_table_hint": tool.get("motherduck_table_hint"),
            "cypher_template": cypher,
            "bound_parameters": bound,
        }
        if cypher:
            plan["neo4j_runtime"] = query_neo4j(cypher, bound)
        plans.append(plan)
    return plans


def graph_rule_ids_for(agent_name: str) -> list[str]:
    return list(_agent_view(load_opportunity_knowledge_graph(), agent_name).get("rule_ids", []))


def _load_schema_from_neo4j() -> dict[str, Any]:
    properties = query_neo4j(
        "MATCH (n) "
        "WITH labels(n)[0] AS label, keys(n) AS keys "
        "UNWIND keys AS property "
        "RETURN label, collect(DISTINCT property) AS properties "
        "ORDER BY label",
        {},
        limit=80,
    )
    relationships = query_neo4j(
        "MATCH (a)-[r]->(b) "
        "RETURN DISTINCT labels(a)[0] AS from_label, type(r) AS edge, "
        "labels(b)[0] AS to_label "
        "ORDER BY edge",
        {},
        limit=120,
    )
    entities = [
        {
            "entity": _entity_name(row.get("label", "")),
            "neo4j_label": row.get("label"),
            "properties": row.get("properties") or [],
        }
        for row in properties.get("records", [])
        if row.get("label")
    ]
    rels = [
        {
            "edge": row.get("edge"),
            "from": _entity_name(row.get("from_label", "")),
            "to": _entity_name(row.get("to_label", "")),
            "meaning": _relationship_meaning(row.get("edge")),
        }
        for row in relationships.get("records", [])
        if row.get("edge")
    ]
    return {
        "status": properties.get("status")
        if properties.get("status") == relationships.get("status")
        else "partial",
        "entities": sorted(entities, key=lambda item: item["entity"]),
        "relationships": rels,
    }


def _load_agent_nodes_from_neo4j() -> dict[str, dict[str, Any]]:
    result = query_neo4j(
        "MATCH (a:Agent) "
        "RETURN a.agent_id AS agent_id, a.role AS role, a.task_id AS task_id, "
        "a.mandatory AS mandatory, a.min_inputs AS min_inputs, "
        "a.handoff_output AS handoff_output "
        "ORDER BY a.agent_id",
        {},
        limit=30,
    )
    nodes = {}
    for row in result.get("records", []):
        role = row.get("role")
        if role:
            nodes[role] = row
    return nodes


def _load_rule_routes_from_neo4j() -> list[dict[str, Any]]:
    result = query_neo4j(
        "MATCH (rr:`Risk Rule`) "
        "OPTIONAL MATCH (rr)-[:OWNED_BY_AGENT]->(a:Agent) "
        "OPTIONAL MATCH (rr)-[:CALLS_API]->(api:APIFunction) "
        "OPTIONAL MATCH (rr)-[:REQUIRES_APPROVAL]->(h:HumanApproval) "
        "RETURN rr.rule_id AS rule_id, rr.risk_type AS risk_type, "
        "rr.trigger_condition AS trigger_condition, rr.severity AS severity, "
        "rr.required_action AS required_action, rr.owner_agent AS owner_agent_field, "
        "a.agent_id AS agent_id, a.role AS agent_role, "
        "collect(DISTINCT api.api_id) AS api_ids, "
        "collect(DISTINCT h.approval_id) AS approval_ids "
        "ORDER BY rr.rule_id",
        {},
        limit=80,
    )
    return result.get("records", [])


def _build_agent_view(
    agent_name: str,
    agent_nodes: dict[str, dict[str, Any]],
    rule_routes: list[dict[str, Any]],
) -> dict[str, Any]:
    view = AGENT_VIEWS[agent_name]
    neo4j_role = AGENT_ALIASES.get(agent_name, agent_name)
    graph_agent = agent_nodes.get(neo4j_role, {})
    min_inputs = graph_agent.get("min_inputs") or view["min_inputs"]
    rule_ids = _rule_ids_from_routes(neo4j_role, graph_agent, rule_routes) or view["rule_ids"]
    entity_access = _entity_access_from_inputs(min_inputs, view["entities"])
    return {
        "agent_name": agent_name,
        "neo4j_agent_role": neo4j_role,
        "neo4j_agent_id": graph_agent.get("agent_id") or view["neo4j_agent_id"],
        "task_id": graph_agent.get("task_id") or view["task_id"],
        "mandatory": graph_agent.get("mandatory"),
        "mission": view["mission"],
        "business_steps": _business_steps_for(agent_name),
        "entity_access": entity_access,
        "rule_ids": rule_ids,
        "graph_rule_routes": [
            route for route in rule_routes
            if route.get("rule_id") in set(rule_ids)
        ],
        "function_calling_policy": _function_policy_for(agent_name),
        "function_tools": _function_tools_for(agent_name, min_inputs),
        "output_contract": _output_contract_for(agent_name),
        "handoff_output": graph_agent.get("handoff_output") or view["handoff_output"],
    }


def _business_steps_for(agent_name: str) -> list[str]:
    agent_name = _canonical_agent_name(agent_name)
    if agent_name == "Data & Finance Agent":
        return [
            "Use KG schema to identify Contract -> Order -> CashFlowMonth context.",
            "Query MotherDuck source tables for the actual selected opportunity.",
            "Compute screening, feasibility, cashflow pressure, funding need, and AI/NLP text signals.",
        ]
    if agent_name == "Risk & Compliance Agent":
        return [
            "Use KG schema for RiskRule, Alert, and HumanApproval routing.",
            "Validate risk flags against MotherDuck source fields and KG rule semantics.",
            "Return only graph-supported risk flags and required actions.",
        ]
    return [
        "Use KG schema for CreditProfile, BankProduct, APIFunction, and approval gates.",
        "Query MotherDuck credit/bank/API tables for the selected opportunity.",
        "Build advisory Decision Card; Founder remains final approver.",
    ]


def _function_policy_for(agent_name: str) -> list[str]:
    agent_name = _canonical_agent_name(agent_name)
    common = [
        "Use Neo4j graph model for context/routing; use MotherDuck for runtime rows.",
        "Retrieve only the entities declared in this agent view.",
        "After AI output, verify rule IDs and approval gates against source fields.",
    ]
    if agent_name == "Risk & Compliance Agent":
        return common + ["Do not create risk flags unless source data supports a KG rule."]
    if agent_name == "Decision & Partner Agent":
        return common + ["Do not approve; only recommend and expose Founder approval gates."]
    return common


def _function_tools_for(agent_name: str, min_inputs: list[str]) -> list[dict[str, Any]]:
    tools = []
    for table in min_inputs:
        tools.append(
            {
                "tool_name": f"motherduck_select_{_tool_name(table)}",
                "source": "MotherDuck",
                "motherduck_table_hint": table,
                "purpose": f"Fetch runtime observations from {table}.",
                "cypher_template": None,
            }
        )
    tools.append(
        {
            "tool_name": "neo4j_schema_context",
            "source": "Neo4j Knowledge Graph model",
            "motherduck_table_hint": None,
            "purpose": "Read graph schema paths, rules, API functions, and approval routing for this agent.",
            "cypher_template": _cypher_for(agent_name),
        }
    )
    return tools


def _output_contract_for(agent_name: str) -> list[str]:
    agent_name = _canonical_agent_name(agent_name)
    if agent_name == "Data & Finance Agent":
        return ["opportunity_profile", "screening", "finance", "ai_nlp_tool_output", "handoff_payload"]
    if agent_name == "Risk & Compliance Agent":
        return ["applicable_risk_flags", "risk_level", "guardrail_note", "evidence_used"]
    return ["recommendation", "conditions", "partner_match", "final_founder_gate"]


def _cypher_for(agent_name: str) -> str:
    agent_name = _canonical_agent_name(agent_name)
    if agent_name == "Data & Finance Agent":
        return (
            "MATCH (cu:Customer)-[:HAS_CONTRACT]->(c:Contract {contract_id:$contract_id}) "
            "OPTIONAL MATCH (c)-[:INCLUDES_ORDER]->(o:Order) "
            "OPTIONAL MATCH (:Company)-[:HAS_CASHFLOW]->(cf:CashFlowMonth) "
            "OPTIONAL MATCH (c)-[:TRIGGERS_RULE]->(rr:`Risk Rule`) "
            "OPTIONAL MATCH (rr)-[:CALLS_API]->(api:APIFunction) "
            "RETURN cu,c,collect(o) AS orders,collect(cf) AS cashflow, "
            "collect(rr) AS triggered_rules,collect(api) AS callable_functions"
        )
    if agent_name == "Risk & Compliance Agent":
        return (
            "MATCH (rr:`Risk Rule`) "
            "OPTIONAL MATCH (rr)-[:OWNED_BY_AGENT]->(a:Agent) "
            "OPTIONAL MATCH (rr)-[:REQUIRES_APPROVAL]->(h:HumanApproval) "
            "RETURN rr,a,h"
        )
    return (
        "MATCH (cp:CreditProfile)-[:SECURED_BY|MATCHED_TO_PRODUCT]->(bp:BankProduct) "
        "OPTIONAL MATCH (rr:`Risk Rule`)-[:REQUIRES_APPROVAL]->(h:HumanApproval) "
        "OPTIONAL MATCH (rr)-[:CALLS_API]->(api:APIFunction) "
        "RETURN cp,bp,collect(h) AS approvals,collect(api) AS functions"
    )


def _agent_view(graph: dict[str, Any], agent_name: str) -> dict[str, Any]:
    agent_name = _canonical_agent_name(agent_name)
    for view in graph.get("agent_views", []):
        if view.get("agent_name") == agent_name:
            return view
    raise KeyError(f"Neo4j knowledge graph view not found for agent: {agent_name}")


def _canonical_agent_name(agent_name: str) -> str:
    return AGENT_ALIASES.get(agent_name, agent_name)


def _rule_ids_from_routes(
    neo4j_role: str,
    graph_agent: dict[str, Any],
    rule_routes: list[dict[str, Any]],
) -> list[str]:
    agent_id = graph_agent.get("agent_id")
    ids: list[str] = []
    for route in rule_routes:
        owner = route.get("agent_role") or route.get("owner_agent_field")
        if owner == neo4j_role or (agent_id and route.get("agent_id") == agent_id):
            rule_id = route.get("rule_id")
            if rule_id and rule_id not in ids:
                ids.append(rule_id)
    return ids


def _entity_access_from_inputs(
    min_inputs: list[str],
    defaults: list[str],
) -> list[str]:
    entities = list(defaults)
    for table_name in min_inputs:
        entity = SOURCE_TABLE_TO_ENTITY.get(str(table_name))
        if entity and entity not in entities:
            entities.append(entity)
    return entities


def _relationship_meaning(edge: str | None) -> str:
    meanings = {
        "HAS_CONTRACT": "Customer/company context links to a contract observation.",
        "INCLUDES_ORDER": "Contract contains delivery orders that drive feasibility and cashflow.",
        "TRIGGERS_RULE": "A source observation can activate a risk rule.",
        "CALLS_API": "A rule can trigger an API/function call.",
        "REQUIRES_APPROVAL": "A rule or API requires human approval.",
        "SECURED_BY": "Credit profile is secured by a financing/bank product.",
        "MATCHED_TO_PRODUCT": "Credit or bank context maps to partner product options.",
        "APPLIES_FOR": "Customer/contract context applies for a credit profile.",
    }
    return meanings.get(edge or "", "Relationship defined by Neo4j importer model.")


def _ref(value: str) -> str:
    return value[1:] if value.startswith("#") else value


def _entity_name(label: str) -> str:
    return "".join(part for part in label.replace("_", " ").split())


def _tool_name(value: str) -> str:
    return value.lower().replace("_", "")
