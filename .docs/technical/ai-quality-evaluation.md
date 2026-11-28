# AI Quality Evaluation Plan — Groundedness (VT-18)

> **Status**: Plan document only — defines an **offline evaluation layer** on top of the
> existing runtime grounding flag. No code or evaluation assets are delivered by this file.
> **All pass thresholds in §4 are DRAFT — pending approval.** Per NFR-AI-04 and the SRS
> release checklist (§5, item 4: "Phê duyệt ... tiêu chí đánh giá AI"), AI quality
> thresholds become effective **only after the evaluation dataset, measurement method
> and MVP goals have been agreed and the thresholds approved**. Until then they are
> proposals for calibration and must not be used for acceptance.

## 1. Traceability

| Reference | Content | Addressed here |
|---|---|---|
| VT-18 | NFR-AI-01–05 — evaluate groundedness, source-fit and task quality using an **approved** dataset, protocol and thresholds (T, A) | Whole document; execution recorded per §5 |
| NFR-AI-01 | Explain/QA tasks SHALL use accessible source context where appropriate | Dataset bucket A (on-page answerable, §2) |
| NFR-AI-02 | Quality evaluation via an approved dataset and protocol | §2 dataset structure + §3 scoring protocol (proposed, pending approval) |
| NFR-AI-03 | Results SHALL distinguish content quality, source-fit and task completion | Four separate rubric dimensions, never merged into one composite score (SyRS §6.4) |
| NFR-AI-04 | Acceptance thresholds determined **after** agreeing dataset, method and MVP goals | §4 thresholds marked DRAFT — pending approval |
| NFR-AI-05 | No claim that answers are always correct or fully source-proven | §6 reporting constraints |
| SYS-FUN-031 | Prioritize the current page source as answer basis | Bucket A scoring (Groundedness dimension) |
| SYS-FUN-032 | Distinguish source-supported parts from added background knowledge | `expected_citations` + Groundedness/Citation rubric separation |
| SYS-FUN-033 | Express uncertainty when evidence is insufficient | Bucket C + Uncertainty-handling dimension |
| SYS-FUN-034 | Ask clarifying guidance when the question lacks context | Scored inside Usefulness/Uncertainty dimensions (prompt may request clarification) |
| SYS-FUN-035 | Never signal AI success when the operation did not happen | Failures/blocked requests are logged as non-scores, not as low-quality answers |
| SyRS §6.4 | Evaluation dimensions: Relevance, Groundedness/Faithfulness, Uncertainty handling, User-perceived usefulness, Privacy-policy adherence | §3 rubric covers the first four; privacy adherence is enforced functionally (privacy preflight tests), not scored by this protocol — see §6 |

## 2. Current State vs. This Plan

**Runtime (implemented)**: `app/core/ai/grounding.py` exposes `is_grounded` and
conservative **citation-ID validation** — it checks that cited IDs exist in the source
context; it does **not** verify semantic truth of the answer. As noted in
`development/implementation-status.md`: "Grounding checks validate citation IDs
conservatively, not semantic truth."

**This document (proposed, not implemented)**: an offline evaluation layer that measures
the actual quality of end-to-end answers on a curated dataset with human judgment. It
complements, and does not replace, the runtime flag.

## 3. Evaluation Dataset (proposed structure)

**Size**: 50–100 cases at MVP. **Format**: one JSON file (or a directory of files) where
each case follows:

```json
{
  "id": "case-001",
  "task": "explain",                     // explain | translate | summarize | chat
  "source_text": "…real web passage, multi-topic…",
  "question": "What does <term> mean in this passage?",
  "expected_grounded": true,
  "expected_citations": ["p2", "p4"],    // citation IDs expected in a good answer; [] when none expected
  "notes": "optional reviewer guidance, never shown to raters during blind scoring"
}
```

- `source_text` uses **real web excerpts across diverse topics and difficulty levels**
  (news, technical documentation, academic prose, everyday articles), matching what the
  extension actually reads. Synthetic filler text is not acceptable — the dataset must
  reflect real extraction output.
- Each case is pre-annotated before evaluation and stored separately from the answer
  transcripts to enable blind scoring.

**Composition (proposed split — calibration may adjust before approval):**

| Bucket | Share | Content | Expected model behavior |
|---|---|---|---|
| A — On-page answerable | ~60% | The question is fully answerable from `source_text` | Grounded answer with correct citations |
| B — Requires external knowledge | ~25% | A complete answer needs background knowledge beyond the page | Answer must explicitly separate source-supported parts from added knowledge (SYS-FUN-032); `expected_grounded: false` or partial |
| C — Insufficient evidence | ~15% | The page does not contain enough information | Model should express uncertainty / ask for clarification (SYS-FUN-033), not fabricate |

## 4. Scoring Protocol (proposed)

### 4.1 Human scoring (primary)

- **Two raters** score every case independently against the rubric below, using the
  answer transcript + source text only.
- **Blind protocol**: raters do **not** see `expected_grounded`, `expected_citations`
  or `notes` while scoring. Bucket labels are unblinded only in the analysis phase.
- Rubric — each dimension scored **0–2**, reported separately (no composite score,
  per SyRS §6.4):

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| **Groundedness** | Answer contradicts or ignores the source | Partially supported; key claims unsupported | Claims are supported by the provided source |
| **Citation correctness** | Missing/wrong citations where required | Citations present but incomplete or partially mismatched | Citations accurately point to the supporting source segments |
| **Uncertainty handling** | Confidently asserts unverified/insufficient evidence | Hedging present but misplaced or excessive | Correctly expresses uncertainty or asks for clarification when evidence is insufficient |
| **Usefulness** | Does not address the user's question | Partially useful; notable gaps | Directly and clearly helps the user's reading task |

- Inter-rater disagreements of ≥ 2 points on any dimension (or opposite binary verdicts
  such as confident-wrong) are re-adjudicated by discussion with the rubric visible; the
  resolution is noted in the results table.

### 4.2 Semi-automated pre-checks (proposed script)

- **Citation string containment**: a small script checks that every citation ID /
  quoted span in the answer appears in `source_text` (string containment on the source
  passages). This is a cheap sanity gate that catches fabricated citations before human
  scoring; it does **not** judge semantics and never replaces human raters.
- The script flags (does not auto-fail): unknown citation IDs, quotes not found in the
  source, and answers that cite nothing while `expected_grounded` is true.

## 5. Proposed Pass Thresholds (DRAFT — pending approval)

| # | Metric | Proposed threshold (DRAFT) | Scope |
|---|---|---|---|
| AI-01 | Groundedness on bucket A (on-page answerable) | ≥ 85% of cases score Groundedness = 2 | Bucket A |
| AI-02 | Confident-wrong rate | ≤ 2% of all cases — answer asserts a wrong claim as fact with no uncertainty signal (across all buckets) | All cases |
| AI-03 | Uncertainty expression on bucket C | ≥ 90% of insufficient-evidence cases show uncertainty or ask clarification (Uncertainty ≥ 1 with no confident-wrong) | Bucket C |
| AI-04 | Citation precision | ≥ 90% of emitted citations map to source segments that actually support the claim (validated by §4.2 script + human confirmation) | Buckets A–B |

These values are calibration starting points derived from common RAG evaluation
practice; they have **no effect until approved** together with the finalized dataset
(NFR-AI-04). When approved, the approved values — not this table — become normative.

## 6. Process & Reporting

1. **Trigger**: run the full evaluation on every change to the default prompts or the
   default provider/model configuration; spot-check subsets for prompt experiments.
2. **Execution**: generate answers for all cases through the standard request path
   (same preflight, grounding and error handling as production); failures (blocked,
   provider error, empty output) are recorded as **non-scores** with their error code
   (SYS-FUN-035) — they are counted separately, never folded into quality percentages.
3. **Recording**: results (per-case scores, threshold comparisons, disagreement notes)
   are stored in an evaluation results table and referenced from the project decision
   log for each run.
4. **Reporting constraints**:
   - Report the four dimensions separately; a single aggregate score must not replace
     per-dimension inspection (SyRS §6.4).
   - No claim that answers are always correct or that all content is source-proven
     (NFR-AI-05); results are stated as measured percentages on the dataset.
   - **Privacy-policy adherence** (SyRS §6.4 fifth dimension) is verified by the
     functional privacy preflight test suite, not scored in this quality protocol —
     a privacy violation is a functional defect, not a quality score deduction.
5. **Effectivity**: thresholds apply to acceptance only after approval, and any later
   threshold change requires a new approval entry in the decision log.
