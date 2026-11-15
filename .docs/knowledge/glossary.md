# Project Glossary

## 1. Domain Terminology

| Term | Definition |
|---|---|
| **BYOK (Bring Your Own Key)** | A model where the end-user supplies their own API key (e.g. OpenAI or Gemini) to pay for their own LLM compute, eliminating operational API costs for the application developer. |
| **Intelligent Reading Assistant** | The full product name of the system, comprising the Chrome Extension client and the ReadHead-BE API. |
| **SSE (Server-Sent Events)** | An HTTP standard allowing the server to push a one-way stream of events/text chunks to the client over a persistent connection (`text/event-stream`). |
| **Key Vault** | The encrypted backend storage subsystem where user API keys are encrypted with AES-256 at rest and decrypted on the fly for AI requests. |
| **Privacy Mode** | A system operational state where the extension and backend agree not to persist browsing history, URLs, or document extracts. |
| **Comprehension Quiz** | An AI-generated set of multiple-choice questions designed to test and reinforce the user's understanding of an article they just read. |
| **Reading History** | A chronological record of articles read via the browser extension, including dwell time and cached summaries. |
| **Highlight** | A specific text snippet selected and saved by the user on a web page, optionally associated with personal notes and color categories. |
| **Provider Adapter** | An internal abstraction class implementing a uniform interface (`BaseAIProvider`) to communicate with specific AI vendors (OpenAI, Gemini, Anthropic). |
