"""Anthropic agentic loop - tool-calling loop for reviews."""

import asyncio
from typing import Callable
import anthropic
from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, AGENT_MAX_TURNS
from tools import dispatch_tool, TOOLS


def _summarize_tool_input(input_dict: dict | str) -> str:
    """Create a short summary of tool input for progress display."""
    if isinstance(input_dict, str):
        if len(input_dict) > 50:
            return input_dict[:50] + "..."
        return input_dict
    if isinstance(input_dict, dict):
        # For bash, show first 40 chars of command
        if "command" in input_dict:
            cmd = input_dict["command"]
            if len(cmd) > 40:
                return f"bash: {cmd[:40]}..."
            return f"bash: {cmd}"
        # For file operations, show the file path
        for key in ["file_path", "pattern", "path"]:
            if key in input_dict:
                return f"{key}: {input_dict[key]}"
    return str(input_dict)[:50]


async def run_agent(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    progress_callback: Callable[[str], any],
) -> str:
    """
    Run the agentic loop using Anthropic API.

    Args:
        system_prompt: The system prompt for the agent
        messages: List of messages in Anthropic format
        tools: List of tool definitions
        progress_callback: Async callback to report progress

    Returns:
        Final text response from the agent
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    turn_count = 0

    while turn_count < AGENT_MAX_TURNS:
        turn_count += 1

        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=8096,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )

        # Append assistant response to message history
        messages.append({"role": "assistant", "content": response.content})

        # Check stop reason
        if response.stop_reason == "end_turn":
            # Extract final text
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    return block.text
            return ""

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if hasattr(block, "type") and block.type == "tool_use":
                    # Send progress update
                    summary = _summarize_tool_input(block.input)
                    await progress_callback(f"Running: {block.name}({summary})")

                    # Dispatch to tool
                    result = await dispatch_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            # Append tool results and loop
            messages.append({"role": "user", "content": tool_results})
        else:
            # Unexpected stop reason
            return f"[Agent stopped with unexpected reason: {response.stop_reason}]"

    return "[Agent reached maximum turns without completing]"
