"""
LangGraph Agent Workflow
========================
ReAct-pattern agent using LangGraph + OpenAI GPT for database operations.
The agent can list tables, describe schemas, read data, execute SQL,
insert and update records in MotherDuck.
"""

import os
from typing import Annotated, TypedDict
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from functions import ALL_TOOLS

# Load environment variables
load_dotenv()


# =============================================================================
# Agent State
# =============================================================================

class AgentState(TypedDict):
    """State shared across all nodes in the graph.

    messages: The conversation history, using add_messages reducer
              to append new messages instead of overwriting.
    """
    messages: Annotated[list, add_messages]


# =============================================================================
# System Prompt
# =============================================================================

SYSTEM_PROMPT = """Bạn là một AI assistant thông minh chuyên quản lý và truy vấn cơ sở dữ liệu MotherDuck (OPC Database).

Khả năng của bạn:
- Liệt kê tất cả bảng trong database
- Mô tả cấu trúc (schema) của bảng
- Đọc dữ liệu từ bảng
- Thực thi các truy vấn SQL SELECT
- Thêm dữ liệu mới vào bảng
- Cập nhật dữ liệu trong bảng

Quy tắc:
1. Luôn sử dụng tools để truy vấn database, KHÔNG tự bịa dữ liệu.
2. Khi user hỏi về bảng, hãy list_tables trước nếu chưa biết bảng nào có.
3. Khi user hỏi về cấu trúc, hãy describe_table trước khi query.
4. Dữ liệu nhạy cảm (email, phone, tên) sẽ được tự động masked.
5. Trả lời bằng tiếng Việt trừ khi user dùng tiếng Anh.
6. Định dạng kết quả dễ đọc, sử dụng bảng markdown khi phù hợp.
7. Với thao tác ghi (INSERT, UPDATE), hãy xác nhận lại với user trước khi thực thi.
"""


# =============================================================================
# Graph Nodes
# =============================================================================

def create_agent_node(model_with_tools):
    """Create the agent node function with the given model.

    Args:
        model_with_tools: LLM model with tools bound.

    Returns:
        Agent node function.
    """
    def agent_node(state: AgentState):
        """Call the LLM with current state and get a response."""
        messages = state["messages"]

        # Ensure system prompt is always the first message
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)

        response = model_with_tools.invoke(messages)
        return {"messages": [response]}

    return agent_node


def should_continue(state: AgentState) -> str:
    """Determine whether the agent should continue to tools or end.

    Returns 'tools' if the last message has tool calls, otherwise END.
    """
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END


# =============================================================================
# Build Graph
# =============================================================================

def build_graph():
    """Build and compile the LangGraph agent workflow.

    Returns:
        Compiled LangGraph application.
    """
    # Initialize LLM
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        raise ValueError(
            "OPENAI_API_KEY is not set. "
            "Please add your OpenAI API key to the .env file."
        )

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        api_key=api_key,
    )

    # Bind tools to model
    model_with_tools = llm.bind_tools(ALL_TOOLS)

    # Create tool node
    tool_node = ToolNode(ALL_TOOLS)

    # Build the state graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent", create_agent_node(model_with_tools))
    workflow.add_node("tools", tool_node)

    # Set entry point
    workflow.set_entry_point("agent")

    # Add edges
    workflow.add_conditional_edges("agent", should_continue)
    workflow.add_edge("tools", "agent")

    # Compile
    app = workflow.compile()
    return app
