**PROPOSAL ACRONYM :** HEDGE-ExpertAI

**Proposal Name**

**Context-Aware AI Discovery and Recommendation Assistant for the HEDGE-IoT App Store**

|                        |                     |                                                                  |
|------------------------|---------------------|------------------------------------------------------------------|
| **Demonstration Area** | **Demo**            | **Business Use Case**                                            |
| TOPIC 15               | Hedge-IoT App Store | TOPIC 15: AI-Enhanced Data App Discovery & Recommendation Engine |

Abstract

HEDGE-ExpertAI aims to make the HEDGE-IoT App Store easier to explore and understand for non-expert users by introducing a context-aware AI assistant that enables natural-language discovery and recommendation of applications. Building on A Arti Mühendislik's Human-Centric Intelligent Energy Management System with Digital Intelligent Assistant, the project adapts a validated knowledge-base toolkit to the HEDGE-IoT environment. The assistant will combine hybrid retrieval (keyword and similarity) with lightweight LLM reasoning and SAREF-aligned metadata signals to generate short, source-grounded explanations for each recommendation. An automated ingestion and indexing service will keep the catalogue continuously updated as new Apps are published through the official API.

The solution will be delivered as a plug-in and OpenAPI-documented backend, fully integrated with the App Store sandbox. Development follows a six-month plan: M1 establishes the architecture and KPIs; by M3 a working prototype will process real queries on the sandbox dataset; and by M6 a validated, deployable version will meet the final KPIs of findability (≥ 70 % top-2 relevance), latency (\< 5 s), and freshness (≤ 24 h update delay). All components will be containerised, documented, and released under an open-source licence, ensuring reusability across other HEDGE nodes and EU digital marketplaces. By advancing from TRL 5 to TRL 8, HEDGE-ExpertAI will deliver a tangible, human-centric enhancement to the HEDGE-IoT ecosystem and strengthen European capacity for explainable AI and interoperable edge-data services.

**Keywords:** HEDGE-IoT, AI recommendation, conversational assistant, hybrid retrieval, open-source

1\. Technical Quality

**1.1. Alignment**

A Arti Muhendislik aims to contribute to the HEDGE-IoT ecosystem by developing an AI-driven, context-aware assistant that makes the HEDGE-IoT App Store easier to explore and understand for non-expert users. The project, *HEDGE-ExpertAI*, supports HEDGE's objective of lowering the entry barrier to edge-computing services by combining language-understanding and lightweight learning components into a service that can be embedded directly in the HEDGE-IoT App Store.

The proposal directly answers Topic 15 -- "AI-Enhanced Data App Discovery and Recommendation Engine", which belongs to HEDGE's activity category of interoperable and user-centric edge-data services.

HEDGE-ExpertAI delivers:

- an AI chatbox interface that interacts with the App Store through official APIs,

- automatic parsing of application metadata (title, tags, input/output datasets) to infer utility, and

- a plug-in integration compatible with the HEDGE-IoT App Store front end.

The service consumes the HEDGE-IoT App Store's standard metadata schema and leverages SAREF-aligned fields as ranking signals---demonstrating standards awareness while staying within the Topic 15 scope.

By coupling RASA for dialogue management with a Large Language Model (LLM) layer for intent interpretation and short, source-grounded explanations, the solution provides a human-centred discovery experience.

A continuously updated ingestion and indexing pipeline ensures that new Apps are also become searchable, guaranteeing that tangible, demonstrable results can be produced during the six-month project period.

To maximize uptake and reproducibility within the HEDGE-IoT ecosystem, the solution will be documented in a public Git repository aligned with HEDGE-IoT documentation practices (readme, architecture notes, API references, deployment guides and change logs). The repository will include an OpenAPI specification for service endpoints and a concise plugin integration guide for the HEDGE-IoT App Store, ensuring that third parties can install, evaluate and extend the solution without back-end changes.

**1.2. Objectives**

The overall objective of HEDGE-ExpertAI is to design, implement, and validate a context-aware AI assistant that enables conversational discovery and recommendation of applications in the HEDGE-IoT App Store, delivering a working solution by the end of the six-month project.

**Objective 1 -- Develop a functional AI chat interface.** Create a text-based assistant that interprets user requests and returns relevant App suggestions with brief, source-grounded explanations.  
***Target:*** working prototype by month 3; ≥ 70% of pilot queries receive a relevant App within the first two suggestions; average response time \< 5 s on the sandbox dataset.

**Objective 2 -- Build an automatic metadata ingestion and indexing pipeline.** Implement a periodic service that collects and indexes App metadata from the official API.  
***Target:*** implementation complete by month 4; new/updated entries become searchable within **≤** 2 hours of publication (to be decreased according to webhooks to be provided and extended to event-based updates if triggers are provided).

**Objective 3 -- Implement the discovery and ranking engine.** Develop a hybrid retrieval method combining keyword search and ML-based similarity; where available, use SAREF-aligned fields as optional signals. ***Target:*** integrated by month 5; correct retrieval validated on ≥ 50 sample queries defined with the HEDGE-IoT team.

**Objective 4 -- Integrate an expert LLM layer for recommendation.** Add a large-language-model component that is trained on a curated "HEDGE Expert" corpus (App metadata + public HEDGE-IoT topics) to improve intent understanding, generate concise explanations, and issue recommendations aligned with user needs. ***Target:*** integrated by month 5; in pilot testing, ≥ 70% of sessions include at least one accepted recommendation (user clicks or follows), and explanations are judged contextually accurate in **≥** 80% of reviewed cases.

**Objective 5 -- Package and validate the App Store plug-in.** Deliver the assistant as a plug-in compatible with the HEDGE-IoT App Store and run an end-to-end demo. ***Target:*** fully functional plug-in on the sandbox by month 6; ≥ 10 complete user-interaction sessions recorded for validation and qualitative feedback.

These objectives remain specific, measurable, achievable, relevant, and time-bound, and they align with Topic 15's emphasis on AI-enhanced discovery and recommendation.

**Objective 6 -- Open documentation and repository.** Publish and maintain a public Git repository with user- and developer-facing documentation aligned to HEDGE-IoT guidance. ***Target:*** repository live by month 1; include ReadMe, architecture overview, OpenAPI spec, deployment guide, configuration examples, and a ChangeLog updated at least bi-weekly. Provide one short demo video and one quick-start tutorial by month 5. Release the HEDGE-IoT App Store plug-in code under a permissive OSS license, with any model prompts/configs documented for reproducibility.

**1.3. Concept and approach / Project Description**

HEDGE-ExpertAI will be an AI-based Search and Recommendation Assistant that enhances the usability of the HEDGE-IoT App Store. It will help users both find and understand applications by combining intelligent search, recommendation logic, and conversational interaction. The assistant will interpret natural-language queries, retrieve relevant Apps, and recommend those that best match user needs while providing concise, explainable summaries. In doing so, it will directly contribute to HEDGE's goal of making edge-computing services more accessible, interoperable, and human-centered.

App Stores in distributed computing environments often contain a growing catalogue of Apps that differ in scope, terminology, and metadata quality. Non-expert users typically describe their needs in informal language, which current keyword-based search engines interpret poorly. Moreover, as new Apps are added, discovery becomes less efficient, leading to under-use of valuable components. HEDGE-ExpertAI addresses this by introducing a context-aware layer capable of understanding user intent, exploiting existing metadata---including SAREF-aligned fields where available---and maintaining an updated, self-documented index. The result will be shorter discovery time, higher match accuracy, and improved understanding of each App's function within the HEDGE ecosystem.

The system will be implemented as a modular, containerized architecture designed for integration with the existing HEDGE-IoT App Store through standard APIs. It will be composed of three functional layers supported by open-source frameworks and DevOps tools that ensure scalability, reproducibility, and maintainability.

1.  **User Interaction Layer**

The conversational interface will be built with the RASA open-source framework (Python), enabling robust intent classification and entity extraction. RASA's modular pipeline (spaCy or transformer-based embeddings) will be customized using a domain-specific vocabulary derived from the HEDGE App Store metadata and documentation. The layer will handle multilingual text input, manage multi-turn dialogues, and coordinate with backend services through FastAPI endpoints. Front-end integration will occur via a lightweight JavaScript plug-in embedded into the App Store web interface. This plug-in will communicate securely through HTTPS, following OAuth-compatible authentication if required by the App Store environment.

2.  **AI Processing Layer**

This layer will perform reasoning and recommendation.

-- The Expert Recommendation component will leverage a Large Language Model (LLM) integrated via LangChain or an equivalent orchestration library to ensure transparency and modularity. A *HEDGE Expert Corpus* (App metadata, public documentation, and training samples) will be used to fine-tune prompts and improve domain adaptation.

-- The Discovery & Ranking Engine will combine keyword retrieval (Elasticsearch / Whoosh) with vector-based similarity search (FAISS or SentenceTransformers). Embeddings will be generated with open models such as MiniLM or all-MPNet-base-v2, ensuring both speed and openness.

-- Where SAREF-aligned metadata are available, they will serve as optional structured features to strengthen ranking consistency.

-- The reasoning pipeline will generate a ranked list and concise rationales explaining each recommendation. These rationales will be grounded in source metadata rather than opaque model predictions to maintain explainability.

3.  **Data Layer**

The Metadata Ingestion and Indexing Service (Node.js + Python) will periodically harvest data from the App Store API, detect updates through checksums or timestamps, and update the index accordingly. If the HEDGE API later supports event-based webhooks, the system will automatically switch to near-real-time updates. The Search Index will combine a FAISS vector store for dense similarity and an inverted index for keyword matching. Incremental indexing will be scheduled using Celery + Redis workers to maintain responsiveness. All microservices will be containerized with Docker, orchestrated locally through Docker Compose, and later portable to Kubernetes for scaling in the HEDGE-IoT infrastructure.

### **Development methodology and tools**

The solution will be developed following agile iteration weekly sprint cycles, with continuous integration using GitHub Actions for linting, unit testing, and container builds.  
Version control, issue tracking, and documentation will be hosted on a public Git repository, providing:

- an OpenAPI specification of all REST endpoints,

- architecture and deployment guides,

- example configurations and quick-start tutorials,

- regular changelogs and tagged releases.

The LLM and indexing components will be evaluated using standard IR (Information Retrieval) metrics---precision, recall, mean reciprocal rank---and user-centric measures of response latency and satisfaction. Unit and integration tests will cover at least 80% of core functionality.

Data exchange will rely solely on public metadata and user-initiated queries. No personal data will be processed or stored. Logs will be anonymized and retained only for KPI measurement within the project period.

### **Architecture and data-flow overview (Figure 1)**

The solution will operate within two main environments: the HEDGE-IoT App Store Environment, which hosts the Front-end and API, and the HEDGE-ExpertAI Deployment Environment, a Docker-based cluster in a HEDGE-IoT data center or cloud node.

When a user submits a query via the App Store plug-in, the message will travel through HTTPS to the 'Chat & Intent' service, which will extract intent and entities. The processed request will pass to 'Expert Recommendation', where the LLM will reformulate it and call 'Discovery & Ranking'. This engine will consult the Search Index to identify candidate Apps and return results to the recommendation layer, which will append rationales and send a conversational response back to the user.  
Concurrently, the 'Metadata Ingestion Service' will pull or receive updates from the App Store API and refresh the index. Documentation and anonymized telemetry will be exported to a public portal for transparency. Each microservice will expose RESTful endpoints described via OpenAPI, supporting modular testing, reuse, and further integration within the HEDGE-IoT ecosystem.

**1.4. Ambition**

The proposed HEDGE-ExpertAI will advance the HEDGE-IoT ecosystem by introducing the first AI-based search and recommendation layer natively integrated into the App Store infrastructure.  
At present, App Stores within distributed or edge-computing environments rely mainly on manual search, simple keyword matching, or static tagging. These methods do not exploit the growing richness of App metadata nor the contextual information embedded in user queries. While some research prototypes in AI-assisted marketplaces have demonstrated semantic search or rule-based recommender functions, none combine context-aware natural-language understanding, explainable LLM-assisted reasoning, and continuous metadata alignment with SAREF within a deployable, open-source framework.

HEDGE-ExpertAI will move beyond these limitations by:

- transforming the App Store into an interactive discovery environment where users converse with the catalogue instead of navigating static lists;

- providing explainable recommendations generated by an LLM grounded in real App metadata rather than opaque correlations;

- ensuring self-updating awareness of new and modified Apps through an automated ingestion pipeline;

- maintaining standards-aligned interoperability, using SAREF attributes as optional reinforcement signals rather than a dependency;

- producing a publicly documented, open-source reference implementation that can be reused by other HEDGE-IoT verticals or regional deployments.

By embedding intelligence directly into it, HEDGE-ExpertAI will demonstrate the next generation of user-centric, AI-enhanced edge-service discovery.

The assistant will not only accelerate adoption of existing Apps but also serve as a gateway for ecosystem growth: new developers will benefit from clearer visibility of their solutions, while end-users will access personalized recommendations reflecting their context and goals.

This integration will therefore raise the Technology Readiness Level of intelligent service discovery within HEDGE to a demonstrable, deployable solution.

The project combines three innovative elements rarely co-existing in current research or industry tools:

1.  **LLM-driven explainability** embedded into a production-ready recommender system;

2.  **Hybrid retrieval architecture** merging symbolic (keyword, schema) and statistical (embedding) reasoning;

3.  **Continuous learning capability**, allowing the assistant to evolve as new Apps and user interactions accumulate.

Together these elements will position HEDGE-ExpertAI as a flagship demonstrator of how conversational AI can make complex, federated IoT ecosystems truly accessible, transparent, and scalable across Europe.

**2. Impact**

> **2.1. Expected impact and results**

HEDGE-ExpertAI will demonstrate and document a reproducible approach to context-aware AI for standards-aligned digital catalogues. Its contribution lies in validated integration of hybrid retrieval and lightweight LLM reasoning for explainable recommendations in constrained industrial environments. Outcomes will include one open technical report, a public repository with runnable evaluation scripts, and an anonymized test set (≥ 50 labelled queries) published by M6. These deliverables will serve as reference material for DIHs, universities, and SMEs researching conversational discovery, advancing applied AI research in edge-computing and data interoperability. **Indicators:** ≥ 1 open repository; ≥ 1 workshop or conference submission; ≥ 50 reproducible test cases shared.

By project end the assistant will reach TRL 8, proving that AI-assisted discovery and recommendation can operate securely and efficiently on the HEDGE-IoT sandbox. Technical gains include a 25 % reduction in manual catalogue maintenance actions, median query latency \< 5 s, and ≥ 70 % top-2 relevance in pilot searches. The resulting OpenAPI-documented plug-in and integration toolkit (Apache-2.0 licence) will strengthen the HEDGE ecosystem's modularity and accelerate uptake of edge-data services. **Indicators:** validated TRL 8 demonstrator; \< 5 s median response; ≥ 70 % top-2 accuracy; open source toolkit release.

The solution will lower operational costs for platform maintainers and improve visibility of innovative Apps from European SMEs, fostering a fairer and more competitive digital-service market. In the pilot, ≥ 60 % of sandbox Apps will receive at least one qualified visit generated by the assistant, while average user time-to-discovery will decrease by ≥ 30 %. For A Arti Mühendislik, a maintainable module and support offering will sustain one qualified full-time position after the project. Through dissemination in networks such as Green SME, AI EDIH Türkiye, Green eDIH Romania, and the European Cluster Collaboration Platform, exploitation will extend beyond the initial use case, reinforcing Europe's digital sovereignty in trustworthy AI and edge computing. **Indicators:** ≥ 30 % faster app identification; ≥ 60 % app exposure rate; ≥ 1 FTE maintained post-project; ≥ 3 external uptake or demonstration events.

> **2.2. Exploitation plan of project results**

The exploitation strategy for **HEDGE-ExpertAI** aims both to sustain the developed solution and to promote the broader HEDGE-IoT ecosystem. By embedding an intelligent assistant directly in the App Store, every user interaction becomes a live demonstration of HEDGE-IoT's interoperability and openness. The assistant thus functions as an **AI ambassador**, translating HEDGE-IoT's architecture and standards into an accessible experience for non-expert users.

Exploitation will follow three complementary pathways: **(1) Open-source release:** the plug-in, backend, and integration toolkit will be published under an open-source license, enabling reuse by other HEDGE nodes and related EU marketplaces. **(2) Professional services:** A Arti Muhendislik will provide installation, adaptation, and maintenance support, creating a self-sustaining business channel and ensuring continuity after the project. **(3) Knowledge and network exchange:** documentation and lessons will be shared through HEDGE-IoT channels and European networks such as GreenSME, AI EDIH Türkiye, Green eDIH Romania, and the ECCP, expanding visibility to DIHs, SMEs, and clusters interested in edge-AI applications.

Primary target groups include operators of IoT and energy-data marketplaces, DIHs, and SMEs requiring accessible discovery tools. Secondary beneficiaries are digital-twin and sustainability platforms that face similar catalogue-management challenges. Post-project, A Arti Muhendislik will maintain at least one full-time expert for user support and further development, guaranteeing that the results---and HEDGE-IoT's vision---remain operational and visible beyond the funding period.

**3.1. Work plan**

2.  **Description of individual tasks**

|                                                                                                                                                                                                    |                                                                                                                                                                                                   |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Task 1: Project Coordination, IPR and Communication Management                                                                                                                                     |                                                                                                                                                                                                   |
| Participant                                                                                                                                                                                        | Role                                                                                                                                                                                              |
| A Arti Muhendislik                                                                                                                                                                                 | coordinate the project and establish technical/legal baselines: requirements, KPI/TRL path, risks, IPR/ethics, HEDGE-API--aligned architecture/data-flow, sandbox access, repositories and CI/CD. |
| **Objectives:** To ensure smooth implementation and communication with the HEDGE-IoT consortium; complete the project setup by M1; manage IPR, reporting and dissemination throughout the project. |                                                                                                                                                                                                   |

|                                                                                                                                                                                                                                                                                                                                                                                                                   |                                                                                                                                                                                                                                                                                             |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Task 2: System Design and Core AI Development                                                                                                                                                                                                                                                                                                                                                                     |                                                                                                                                                                                                                                                                                             |
| Participant                                                                                                                                                                                                                                                                                                                                                                                                       | Role:                                                                                                                                                                                                                                                                                       |
| A Arti Mühendislik                                                                                                                                                                                                                                                                                                                                                                                                | Design and implement the assistant's functional core including the chat and intent-understanding layer (RASA + LLM), metadata ingestion and indexing pipeline with optional SAREF alignment, discovery and ranking engine, and first sandbox integration with a minimal front-end interface |
| **Objectives:** Deliver the functional core enabling the Mid-Term Review: complete architecture and data-flow design; working conversational logic returning concise, source-grounded responses; automated metadata ingestion from the App Store API; hybrid retrieval and ranking verified on the sandbox; and containerized, tested services prepared for subsequent integration.                               |                                                                                                                                                                                                                                                                                             |
| **Description of work:** AI-stack development, implementing the RASA pipeline and LLM layer, and designing the retrieval and ranking methods. Developing the prototype front-end, ensures API connectivity with the App Store, and assists with metadata-service integration. Deploying local and cloud environments, containerizes components, and maintaining CI/CD pipelines and monitoring for the prototype. |                                                                                                                                                                                                                                                                                             |

|                                                                                                                                                                                                                                                                                                                                                                                                                                                 |                                                                                                                                                                            |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Task 3: Integration, Validation and Deployment                                                                                                                                                                                                                                                                                                                                                                                                  |                                                                                                                                                                            |
| Participant                                                                                                                                                                                                                                                                                                                                                                                                                                     | Role:                                                                                                                                                                      |
| A Arti Muhendislik                                                                                                                                                                                                                                                                                                                                                                                                                              | integrate the assistant with the HEDGE-IoT App Store sandbox, deploy on a secure, containerized cloud setup, and validate KPIs for latency, relevance, and data freshness. |
| **Objectives:** To integrate the assistant with the HEDGE App Store sandbox, validate KPIs and prepare deployment on a secure cloud. by M5 have a stable build fully wired to the sandbox API and UI, median response time \< 5 s, ≥ 70% top-2 relevance on the pilot set, and catalogue refresh ≤ 24 h.                                                                                                                                        |                                                                                                                                                                            |
| **Description of work:** Completing UI adaptation and front-end/API wiring, executing end-to-end functional tests, and fixing usability issues; Handling cloud deployment, orchestration, monitoring, and security hardening in an ISO 27001-certified data center, and verifying uptime/latency; fine-tuning intent and ranking parameters on sandbox data, aligning logs and metrics to KPI measurements, and supporting automated test runs. |                                                                                                                                                                            |

|                                                                                                                                                                                                                                                                                                                                        |                                                                                                                                                                      |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Task 4: Demonstration, Dissemination and Exploitation                                                                                                                                                                                                                                                                                  |                                                                                                                                                                      |
| Participant                                                                                                                                                                                                                                                                                                                            | Role:                                                                                                                                                                |
| A Arti Mühendislik                                                                                                                                                                                                                                                                                                                     | prepare and demonstrate the final validated version of the assistant, support evaluation, and conduct dissemination and exploitation activities linked to HEDGE-IoT. |
| **Objectives:** deliver a fully operational, validated plug-in on the sandbox with complete documentation, demonstration materials, and initial exploitation actions through professional and open channels.                                                                                                                           |                                                                                                                                                                      |
| **Description of work:** Ensuring conversational accuracy and preparing the final test dataset and evaluation summary; Managing the demonstration setup and supports UI refinements for clarity and usability; Finalizing hosting, monitoring, and deployment documentation, and ensures stable operation during pilot demonstrations. |                                                                                                                                                                      |

3.1.3. List of deliverables

|                |                                                  |         |               |                                |
|----------------|--------------------------------------------------|---------|---------------|--------------------------------|
| Deliverable No | Deliverable Name                                 | Task No | Nature^\[1\]^ | Dissemination level^\[2\]^     |
| D1.1           | Project Management & IPR Handbook                | T1      | R             | Internal for Project Consortia |
| D2.1           | System Architecture Specification                | T2      | R             | Internal for Project Consortia |
| D2.2           | Functional Core Prototype & Mid-Term Report      | T2 + T1 | P             | Internal for Project Consortia |
| D3.1           | Validated Sandbox Deployment & Test Report       | T3      | R             | Internal for Project Consortia |
| D4.1           | Final Report and Open-Source Integration Toolkit | T4 + T1 | R + P         | Public                         |
| D4.2           | Workshop Presentation for HEDGE-IoT Consortium   | T4      | D             | Public                         |

> 3.1.4. List of milestones

|              |                                           |                |                                                      |
|--------------|-------------------------------------------|----------------|------------------------------------------------------|
| Milestone No | Milestone Name                            | Tasks involved | Means of verification                                |
| M1           | Project Setup and Architecture Approval   | T1, T2         | Delivery of D1.1 + approved architecture document    |
| M2           | Mid-Term Functional Prototype Review      | T2 + T1        | Delivery of D2.2 (Mid-Term Report & prototype demo)  |
| M3           | Final Validated Release and Dissemination | T3, T4         | Delivery of D4.1 + D4.2 and approval in Final Review |

> 3.1.5. Technological Risks

R1 App Store API delay -- develop against mock API , use versioned adapter and contract tests, fallback to manual metadata import if needed. R2 Latency above 5 s -- use local embeddings and caching, timeouts and RASA-only fallback, load tests. R3 Retrieval quality below target -- label ≥ 50 queries with HEDGE, run offline evaluation and tuning, use hybrid weights and optional SAREF signals. R4 LLM hallucinations -- restrict to source-grounded answers, require rationale, limit length, fallback to link-only output on low confidence. R5 GDPR/security non-compliance -- own server in ISO 27001 EU data centre, TLS 1.2+, RBAC, key rotation, no PII, anonymised logs, DPIA. R6 Integration effort higher than planned -- build early UI stub, share OpenAPI contract, hold weekly syncs, use feature flags. R7 Scope or schedule overrun -- freeze scope, prioritise KPIs, bi-weekly burn-down. Risks reviewed bi-weekly; any KPI deviation triggers corrective action next sprint.

Intellectual Property and Ethical Issues

**IP & licensing.** Foreground IP will be owned by **A Arti Mühendislik**. The core components (plug-in, ingestion/indexing, evaluation scripts) will be released **open-source (Apache-2.0)** to enable reuse in HEDGE; third-party OSS respected under original licences. Novel, standalone modules (e.g., explanation pipeline) may be assessed for **utility patent** only if compatible with the open stack.

**Data protection & ethics.** No personal data are required; only public App metadata are processed. Pilot deployment will run on our **owned server** hosted in an **EU, ISO/IEC 27001-certified** data center; **TLS/RBAC**, key rotation, and **anonymized logs** for KPI checks only. If scope changes, a **DPIA** will be performed; all actions align with **GDPR** and Horizon Europe ethics guidance.

**Declaration.** There is **no active engagement** with any **HEDGE-IoT consortium partner** or the **business use-case provider** for the addressed BUC prior to this proposal.

