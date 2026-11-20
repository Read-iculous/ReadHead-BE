# 01 — Project Awareness

## Project Overview
ReadHead-BE is the backend API server for the ReadHead platform. The project is in its **early stage** —
specification documents exist but no code has been written yet. The agent's role is to help build
the backend according to those specifications.

## Position in the System
```
[Client: Web / Mobile App]
        ↓ HTTP/REST
[ReadHead-BE] ← This repository
        ↓
[PostgreSQL Database]
```

## Source Specification Files (docx)
The following files contain the original project specifications, located at the repo root:
| File | Content |
|---|---|
| `BRS.docx` | Business Requirements Specification |
| `SRS.docx` | Software Requirements Specification |
| `SyRS.docx` | System Requirements Specification |
| `StRS.docx` | Stakeholder Requirements Specification |
| `OpsCon.docx` | Operational Concepts Document |
| `RTM.docx` | Requirements Traceability Matrix |

> Content is gradually being extracted into `.docs/` in markdown format.
> Always prefer reading `.docs/` first. Only reference `.docx` files when the information
> is not yet available in `.docs/`.

## Project Status
- [x] Specification documents: ✅ Available (docx)
- [ ] `.docs/` markdown: 🔄 In progress
- [ ] Backend code: ⏳ Not started
- [ ] Tests: ⏳ Not started
- [ ] Deployment: ⏳ Not started

## Key Constraints
See `.docs/knowledge/constraints.md` for technical and business constraints.
