# 00 — Core Principles

These are the foundational principles. The agent must follow them **in every situation, without exception**.

## 1. Research First
Before writing any code, read the relevant documentation in `.docs/`.
Never start from "I think it should work like this."

## 2. No Guessing
When unsure about:
- A table's schema → read `.docs/database/schema.md`
- An API contract → read `.docs/api/endpoints.md`
- Business logic → ask the user

A wrong guess is worse than doing nothing.

## 3. Minimal Surface
Only modify files that are genuinely relevant to the task.
Do not refactor unrelated code or "improve" logic that wasn't requested.

## 4. Document as You Go
Any change to architecture, API, or database schema must be reflected in `.docs/`
within the same session. Do not leave documentation technical debt.

## 5. Ask Before Proceeding
If a task is ambiguous or missing critical information, stop and ask rather than
making assumptions. List clearly what is still unclear.

## 6. Fail Loudly
When an error or conflict is encountered, report it immediately with full context.
Do not silently skip or workaround without explanation.

## 7. Respect Boundaries
- Do not read, write, or modify files outside the task scope
- Do not add dependencies that weren't requested
- Do not modify production environment configuration
