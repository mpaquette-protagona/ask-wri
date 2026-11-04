# AskWRI: Technical Environment Document

---

## Project Technical Summary

- **Project Name**: AskWRI - World Resources Institute
- **Primary Runtime Environment**: Cloud
- **Cloud Provider**: AWS
- **Target Deployment Model**: Serverless and managed services (Bedrock, AgentCore); containers (ECS Fargate) permitted
- **Customer Team Experience**: Python (FastAPI), TypeScript (Next.js), Terraform, ECS Fargate, hybrid search (BM25 plus vector), LlamaIndex, RAG evaluation

---

## Programming Languages

### Required Languages

| Language | Version | Purpose | Rationale |
|----------|---------|---------|-----------|
| Python | 3.12+ | Agents, ingestion, retrieval, evaluation | Matches WRI's search service |

### Permitted Languages

| Language | Conditions for Use |
|----------|-------------------|
| TypeScript | UI or infrastructure code |

---

## Frameworks and Libraries

### Preferred Services

| Service | Version | Domain | Rationale |
|-------------------|---------|--------|-----------|
| Amazon Bedrock | Current | Models for generation, embeddings, translation | Customer direction |
| Amazon Bedrock AgentCore | Current | Agent runtime and multi-agent workflows | Customer direction |
| AWS Lambda (Optional) | Current | Serverless compute environment | Customer direction |
| Amazon ECS (Optional) | Current | Containerized compute environment | Customer direction |


---

## Cloud Environment

### Cloud Provider

- **Primary Provider**: AWS
- **Account Structure**: One sandbox account per team
- **Regions**: Sandbox default; use cross-region inference if a model isn't available

### Suggested Building Blocks

| Need | Options |
|------|---------|
| Document storage | Amazon S3 |
| Retrieval | Bedrock Knowledge Bases (S3 Vectors, OpenSearch Serverless, or Aurora pgvector) or custom |
| Agents | AgentCore Runtime, Memory, Gateway, Observability |
| Grounding checks | Bedrock Guardrails |

---

## Preferred Technologies and Patterns

### Architecture Patterns

| Pattern | When to Use | When Not to Use |
|---------|-------------|-----------------|
| RAG with required citations (pgvec preferred) | All answers and briefings | Never skip |
| Serverless first | New components | Parts that need to mirror WRI's Fargate services |

### Data and Evaluation

- **Corpus**: Sample 50 to 150 of the 1,348 public documents at https://www.wri.org/resources/type/research-65, or use WRI's dump.
- **Metadata**: Title, URL, date, program, language.
- **Citations**: Title, link, and passage or page.
- **Evaluation**: 15 to 25 test questions with expected sources; report recall and precision; include one unanswerable question.

### Security Basics

- Least-privilege IAM roles
- No secrets in code
- Private, encrypted S3 buckets
