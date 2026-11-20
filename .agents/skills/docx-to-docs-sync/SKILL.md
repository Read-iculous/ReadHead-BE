---
name: docx-to-docs-sync
description: >-
  Use this skill when extracting and converting content from .docx specification
  files (BRS, SRS, SyRS, StRS, OpsCon, RTM) into .docs/ markdown files for
  ReadHead-BE. Activate when the user says "extract from docx", "add content from
  SRS", "convert spec to docs", or "update docs from specification files".
---

# Docx-to-Docs Sync — ReadHead-BE

## Overview
The project has `.docx` specification files at the root. Their content needs to be gradually
extracted into `.docs/*.md` so the agent can read it efficiently. This is a semi-manual process —
the agent handles formatting and organization, but the user must supply the raw content from the
docx files (the agent cannot read `.docx` directly).

## Mapping: Docx → Docs Target

| Source file | Target file | Key content |
|---|---|---|
| `BRS.docx` | `.docs/project-overview.md` | Business goals, stakeholders, success metrics |
| `BRS.docx` | `.docs/knowledge/constraints.md` | Business constraints, non-functional requirements |
| `SRS.docx` | `.docs/api/endpoints.md` | Functional requirements → API endpoints |
| `SRS.docx` | `.docs/database/schema.md` | Data requirements → DB schema |
| `SyRS.docx` | `.docs/architecture/overview.md` | System architecture |
| `SyRS.docx` | `.docs/technical/auth-flow.md` | Authentication & security requirements |
| `StRS.docx` | `.docs/project-overview.md` (stakeholders section) | Stakeholder needs |
| `StRS.docx` | `.docs/knowledge/glossary.md` | Domain terminology |
| `OpsCon.docx` | `.docs/development/workflows.md` | Operational workflows |
| `OpsCon.docx` | `.docs/architecture/decisions.md` | Operational decisions |
| `RTM.docx` | `.docs/knowledge/decisions.md` (reference only) | Traceability matrix |

## Extraction Process

### Step 1: User Provides Content
The agent cannot read `.docx` files directly. The user should:
- Open the `.docx` file and copy the relevant section
- Paste it into the chat, **or**
- Export the docx to `.txt` and let the agent read that file

### Step 2: Agent Analyzes and Classifies
From the raw content, the agent will:
1. Identify which section it belongs to (business rules / data schema / API / architecture)
2. Map it to the correct `.docs/` file
3. Format it into clean, structured markdown

### Step 3: Write to the Docs File
Append or update content in the correct file, correct section, using the correct format.

### Step 4: Mark the Source
Add a source comment so it's traceable:
```markdown
<!-- Source: SRS.docx §3.2 — Extracted YYYY-MM-DD -->
```

### Step 5: Verify
- No important information was lost in the conversion
- Markdown is valid and renders correctly
- No sensitive information included (test passwords, internal credentials)

## Standard Output Formats

### Business requirements → project-overview.md
```markdown
## Project Goals
[content from BRS]

## Stakeholders
| Role | Description | Interests |
|------|-------------|-----------|

## Success Metrics
- ...
```

### Functional requirements → api/endpoints.md
```markdown
## POST /api/v1/<path>
<!-- Source: SRS.docx §X.X -->
- **Description**: ...
- **Auth**: ...
```

### Data requirements → database/schema.md
```markdown
## Table: <table>
<!-- Source: SRS.docx §X.X -->
| Column | Type | Nullable | Description |
```

## Important Notes
- **Do not copy verbatim** if the source language is formal or academic — rewrite into clear, action-oriented language
- **Write for agents, not humans**: optimize for fast AI comprehension, not beautiful prose
- **Track extraction progress** in `.docs/knowledge/decisions.md` to know what has and hasn't been extracted yet
