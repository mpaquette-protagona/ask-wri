# AskWRI: Vision Document

## Executive Summary

AskWRI is an agentic AI research assistant on Amazon Bedrock and AgentCore that helps WRI researchers find, synthesize, and cite WRI's published research. Every answer traces to a specific WRI source. It adds tailored briefings, translation, and suggestions for future research across WRI's global offices. WRI already has a prototype; this hackathon builds a self-contained version in a sandbox to explore novel approaches to agentic architectures.

---

## Business Context

### Problem Statement

Finding prior WRI research is slow and incomplete. Researchers rely on site searches, a database covering only 2019 onward, and asking senior staff. As a result:

- Relevant publications get missed, especially older ones without DOIs.
- Researchers struggle to see what WRI has already covered on a topic.
- Junior and senior staff spend time on manual search instead of analysis.
- Research in other languages is hard to use without translations.

Generic chatbots don't help because their answers can't be verified against WRI sources.

### Business Drivers

- 50 years of WRI research is underused because it is hard to search.
- RAG and multilingual models can now ground answers in a trusted corpus.
- WRI's Chief Data and AI Officer backs the project.

### Target Users and Stakeholders

| User Type | Description | Primary Need |
|-----------|-------------|--------------|
| Researchers | WRI research staff, junior and senior | Find and cite relevant WRI work quickly |
| Partnerships / Fundraising | Staff preparing for engagements and proposals | Short, cited briefings on a topic |
| Global Office Staff | Staff working in other languages | Access research in any language |
| WRI Data Lab | Team that owns AskWRI | A pattern they can bring back into their environment |

### Business Constraints

- Every claim must cite a WRI source.
- Answers use only WRI's published research, not the web.
- Public documents only; build in an empty AWS sandbox; 2 days.

### Success Metrics

| Metric | Current State | Target State | Measurement Method |
|--------|--------------|--------------|-------------------|
| Citation traceability | Manual search | 100% of claims cited | Review demo answers |
| Retrieval recall | Prototype target: 75% | Report on a 15 to 25 question test set | Compare to expected sources |
| Time to useful source | Hours to days | Under 1 minute | Timed demo |

---

## MVP Scope

### MVP Objective

Show that a multi-agent assistant can answer questions and produce briefings over a sample of WRI research, with accurate citations.

### MVP Success Criteria

- [ ] Answers cite specific WRI documents (title, link, passage).
- [ ] The assistant says so when the corpus has no answer.
- [ ] A user can get a cited briefing on a topic.
- [ ] Results are shown against a small test question set.

### Features In Scope (MVP)

| Feature | Description | Priority | Rationale for Inclusion |
|---------|-------------|----------|------------------------|
| Corpus ingestion | Load 50 to 150 public WRI documents with basic metadata (provided at event) | Must Have | Required for everything else |
| Cited Q&A | Answers grounded only in the corpus | Must Have | Core value |
| "No answer" response | Flag or decline weakly supported answers | Must Have | Limits hallucination |
| Research briefing | Structured, cited summary of a topic | Must Have | Addresses landscape mapping |
| Multi-agent workflow | Two or more cooperating agents | Optional | Tests the multi-agent approach |
| Translation | Translate passages or briefings on request | Should Have | Supports global offices |
| Research suggestions | Suggest follow-up questions or gaps | Should Have | Differentiator |
| Simple UI | Chat or web interface for the demo | Must Have | User experience |
| Figure and table parsing | Complex document context parsed into the knowledge base  | Should Have | Many useful documents are complex | 


### Features Explicitly Out of Scope (MVP)

| Feature | Reason for Deferral | Target Phase |
|---------|-------------------|--------------|
| Full 1,348 document corpus | Too large for 2 days | Stretch goal |
| Authentication and roles (RBAC) | Not needed in a sandbox | Phase 2 |
| Integration with WRI's prototype | Not accessible from the sandbox | TBD |

### MVP User Journeys

#### Journey 1: Ask a cited question
1. A researcher asks what WRI has published on electric buses in Latin America.
2. The assistant returns a short answer with citations.
3. The researcher opens a citation to verify it.

**Outcome**: Relevant sources found in minutes.
**Limitation vs Full Vision**: Sample corpus only.

#### Journey 2: Get a research briefing
1. A staff member requests a briefing ahead of a partner meeting.
2. The assistant returns a cited summary, key findings, and related publications.
3. Optionally, they ask for it in Spanish.

**Outcome**: A shareable briefing without manual review.
**Limitation vs Full Vision**: Fixed format.

#### Journey 3: Find research gaps
1. A researcher asks where WRI's work on a topic is thin.
2. The assistant summarizes coverage and suggests possible directions, labeled as suggestions.

**Outcome**: A starting map for new work.
**Limitation vs Full Vision**: Gaps may reflect the sample, not WRI's full body of work.

### MVP Constraints and Assumptions

- **Assumption**: WRI provides a document dump before the event. - **Risk if wrong**: Teams lose time collecting documents.
- **Assumption**: The sample includes some non-English documents. - **Risk if wrong**: Translation and multilingual search can't be shown.

### MVP Definition of Done
Bostonboy#00

- [ ] All Must Have features demonstrated
- [ ] Every answer and briefing shows citations
- [ ] At least one unanswerable question is correctly declined
- [ ] Deployed in the sandbox and reproducible from the team repo

---

## Risks and Dependencies

### Key Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Corpus not ready | Medium | High | Agree on a sample list early; have a download script |
| Poor PDF parsing | High | Medium | Start with text-heavy documents |
| Weakly grounded answers | Medium | High | Require citations; test the "no answer" path early |
| Mistranslation | Medium | Medium | Label translations and show the original |
| Multi-agent setup takes too long | Medium | Medium | Get single-agent Q&A working first |

### External Dependencies

- Public document dump - WRI Data Lab - Offered
- Sandbox accounts with Bedrock and AgentCore access - AWS - To confirm
- Example test questions - WRI research staff - Not started

### Open Questions

- [ ] What format will the document dump use (PDFs, text, metadata file)?
- [ ] How will citations recall and retrieval be evaluated? Is there ground truth data? 
- [ ] Should different users have access to different data for retrieval? (RBAC)
- [ ] Should the sample focus on one program (such as Cities) or a mix? 
- [ ] Should the knowledge base be split by different sub-sections, or a common pool for all source documentation? (metadata-filtering)
- [ ] Can WRI share 15 to 25 test questions with expected sources? (ground truth)
