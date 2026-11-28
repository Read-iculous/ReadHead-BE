# 01 — Project Awareness

## Project Overview
ReadHead-BE is the backend API server for the ReadHead platform. The project is in its **early stage** —
the backend source now implements the documented roadmap except the explicitly deferred BE-17 automated test suite. See `.docs/development/implementation-status.md` for verification limits and remaining client/provider setup.

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
- [x] Backend code: implemented for BE-01–BE-16 and BE-18
- [ ] Automated error/integration tests and coverage: explicitly deferred by the user; basic successful runtime checks performed
- [ ] Deployment: ⏳ Not started

## Key Constraints
See `.docs/knowledge/constraints.md` for technical and business constraints.
