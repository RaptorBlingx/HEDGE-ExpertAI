Subject: HEDGE-ExpertAI — Progress Update (April 2026)

Hi,

I wanted to give you an update on where we are with the HEDGE-ExpertAI project. We are now at month 4 of 6.

**Quick reminder:** HEDGE-ExpertAI is the AI assistant we are building for the HEDGE-IoT App Store. It lets users ask in plain language what kind of IoT app they need, and it finds and recommends the most relevant ones with short explanations. Think of it like a smart search + recommendation chatbot for the App Store.


## What I Did So Far

The core system is built and working. Here is what we have:

- **The full backend** — 6 services that handle everything: understanding what the user is asking, searching and ranking apps, generating recommendations with AI, and keeping the app catalog up to date automatically. All running in Docker containers.

- **The chat widget** — A small plug-in (a JS + CSS file) that can be embedded in any webpage, including the App Store. The file is ready — it just needs to be hosted and linked. Not deployed publicly yet.

- **A testing console** — A web interface running at http://localhost:8080 where you can browse the app catalog and test the chat at the same time. Useful for demos and internal testing.

- **Automated catalog sync** — The system checks for new or updated apps every 2 hours and re-indexes them automatically. No manual work needed.

- **Documentation** — Full set of guides (architecture, deployment, development, API reference, plugin integration, etc.), plus OpenAPI specs for all services.

- **CI/CD pipeline** — Automated testing and building on every code push.

- **Evaluation framework** — 50+ test queries to measure how well the search works, with automated scoring.


## Results

I just re-ran the evaluation (53 queries, live system) and got the same numbers:

On search relevance, the target was ≥ 70% — we got 71.7%. All 53 test queries returned results with zero errors, and 90.9% of the time the right app appears somewhere in the top 5. On catalog freshness, the target was within 24 hours — we refresh every 2 hours. On search speed, the median is around 60 ms — but see the note below, this is not the full picture.

**Important note on speed:** The 60 ms is the time for the search/ranking step only — finding and ranking the apps. The full end-to-end experience (from the moment you send a message to the moment the AI finishes writing its response) is much longer. On our current setup (CPU only, no GPU, limited server resources), it can take around 90 seconds or more depending on how long the response is. This is because the AI model generates text slowly on CPU — roughly 3 words per second. If the proposal KPI of "< 5 seconds" refers to the full chat response time, we are not meeting that with the current setup. I am looking into options to improve this (smaller model, quantization, or GPU access), but I want to be honest: achieving under 5 seconds end-to-end on CPU-only infrastructure is very unlikely. This needs to be discussed.

The 71.7% relevance is the number I am confident about — it was tested and re-tested.


## Current State

- Version 0.1.0 released in March, with additional improvements since then (security, caching, feedback tracking, real API client).
- The system is validated and working on our sandbox environment.
- Right now it runs against a mock version of the App Store (46 sample apps). The code to connect to the real App Store API is already written and ready.
- Running on a small server (5 GB). Some optional AI features are turned off to fit within this limit — they can be enabled on a bigger machine.

On deliverables: D1.1 (Project Management), D2.1 (Architecture), D2.2 (Core Prototype), and D3.1 (Evaluation Report) are all done. D4.1 (Final Report) is in progress, and D4.2 (Workshop Presentation) has not started yet.


## Next Steps (Month 5–6)

1. Connect to the real HEDGE-IoT App Store API — the code is ready, we need API access.
2. Re-run evaluation with real data and adjust if needed.
3. Create the demo video and quick-start tutorial (committed in proposal for Month 5).
4. Prepare the final deliverables (Final Report + Workshop Presentation).
5. If we get a bigger server, enable the advanced ranking model for better accuracy.


## Risks & Notes

- **Real API access** — We are ready to connect, but we need the credentials and access. Any delay on this could push the final validation.
- **End-to-end response speed** — This is the main open issue. The full chat response time is around 90 seconds on the current CPU-only server. If the proposal KPI means end-to-end chat, we are not meeting it. I am working on options (lighter model, quantization, GPU), but I want to flag this now rather than at the end.
- **Server size** — The 5 GB limit blocks some optional AI features. A bigger server would improve both accuracy and speed.
- **Cross-domain queries** — When a query spans multiple categories (like "smart home"), results are less precise. This is a known limitation.


Let me know if you have questions or need more details on anything.

Best regards
