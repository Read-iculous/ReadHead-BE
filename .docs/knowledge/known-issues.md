# Known Issues & Edge Cases

## 1. Registry Format
Entries are added here as edge cases or technical quirks are discovered during development.

---

## 2. Documented Issues

### [ISSUE-001] Client Disconnect During SSE Streaming
- **Discovered**: 2026-11-14
- **Severity**: Medium
- **Description**: If a user closes the Chrome Extension side panel or switches tabs while an LLM streaming response is in flight, the HTTP connection is aborted by the client. If unhandled, this could raise `asyncio.CancelledError` or leave open background streaming loops consuming upstream tokens.
- **Workaround / Solution**: In FastAPI route handlers for SSE, wrap generation loops with `try ... except asyncio.CancelledError:` and explicitly close upstream generator connections upon cancellation.

### [ISSUE-002] Upstream Token Limits on Long Web Pages
- **Discovered**: 2026-11-14
- **Severity**: Low
- **Description**: Extracting an entire Wikipedia page or PDF could exceed the context window of smaller models or incur high latency.
- **Workaround / Solution**: The `ai_service` truncates or chunks page text to a safe maximum token count (e.g. 16k tokens) before constructing prompts, prioritizing text near the user's active selection.
