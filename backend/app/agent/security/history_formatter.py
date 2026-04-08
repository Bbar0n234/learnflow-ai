from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage


def format_for_classifier(messages: list[BaseMessage], current_content: str) -> str:
    """Format conversation history + current message for the security classifier.

    Produces XML-wrapped text with role prefixes for each message.
    """
    lines: list[str] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            prefix = "[USER]"
        elif isinstance(msg, AIMessage):
            prefix = "[ASSISTANT]"
        elif isinstance(msg, ToolMessage):
            name = msg.name or "unknown"
            prefix = f"[TOOL:{name}]"
        else:
            prefix = "[SYSTEM]"
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        lines.append(f"{prefix} {content}")

    lines.append(f"[USER] {current_content}")

    inner = "\n".join(lines)
    return f"<conversation_history>\n{inner}\n</conversation_history>"
