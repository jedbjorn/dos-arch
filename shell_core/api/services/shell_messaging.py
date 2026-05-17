def _cap_lines(text: str, n: int) -> str:
    lines = text.strip().splitlines()
    if len(lines) <= n:
        return text.strip()
    return "\n".join(lines[:n]) + f"\n… ({len(lines) - n} more lines)"


def _build_message_prompt(message_id, sender_id, sender_name, recipient_id, subject, body, context):
    parts = [f"You have an incoming message from {sender_name} (shell_id={sender_id})."]
    if context:
        parts += ["", "== SENDER CONTEXT (current session) ==", _cap_lines(context, 50)]
    parts += ["", "== MESSAGE =="]
    if subject:
        parts += [f"Subject: {subject}", ""]
    parts += [body.strip(), "", "== INSTRUCTIONS ==",
        "1. Run your session start protocol first.",
        "2. Review the message and context above.",
        f"3. Reply via POST /shell-messages — sender_id={recipient_id}, recipient_id={sender_id}, reply_to_message_id={message_id}",
        f"4. Mark read: PATCH /shell-messages/{message_id}"]
    return "\n".join(parts)
