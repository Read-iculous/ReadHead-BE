"""Normalize conversational roles across provider payloads."""


class HistoryFormatter:
    """Keep system instructions separate and coalesce repeated roles."""

    @staticmethod
    def normalize(messages: list[dict]) -> tuple[str, list[dict]]:
        """Extract trusted system instructions and merge consecutive turns."""
        system = []
        turns: list[dict] = []
        for message in messages:
            role, content = message["role"], message["content"]
            if role == "system":
                system.append(content)
            elif role in {"user", "assistant"}:
                if turns and turns[-1]["role"] == role:
                    turns[-1]["content"] += "\n\n" + content
                else:
                    turns.append(dict(role=role, content=content))
        if turns and turns[0]["role"] == "assistant":
            turns.insert(
                0, dict(role="user", content="Continue this reading discussion.")
            )
        return "\n\n".join(system), turns
