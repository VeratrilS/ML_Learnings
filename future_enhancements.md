# Future Enhancements — High Level Design (HLD)

A roadmap of architectural improvements, system design upgrades, and learning opportunities for the Productivity Automations project.

---

## 1. Message Queue Architecture (Async Processing)

### Current Problem
The Flask API handles LLM calls, email sending, and DB writes **synchronously** in a single request. If the LLM takes 10s, the HTTP request hangs for 10s.

### Proposed HLD
```
┌──────────┐      ┌──────────┐      ┌──────────────┐      ┌──────────┐
│  GitHub   │──▶   │  Flask   │──▶   │  Task Queue  │──▶   │  Worker  │
│  Actions  │      │   API    │      │  (Celery/RQ) │      │ Process  │
└──────────┘      └──────────┘      └──────────────┘      └──────────┘
                       │                                        │
                       ▼                                        ▼
                  Return 202                              LLM + Email
                  (Accepted)                              + DB Write
```

### What You'll Learn
- **Message Queue patterns** (Producer-Consumer)
- **Celery** with Redis as broker
- **Eventual Consistency** — the API returns immediately, the task completes later
- **Retry with exponential backoff** for failed tasks

### Implementation Notes
- Use **Redis** as the message broker (free tier on Upstash)
- Workers process the queue and handle retries
- API returns `202 Accepted` with a task ID for polling

---

## 2. Database Migration to PostgreSQL + Alembic

### Current Problem
- Local dev uses SQLite, Vercel uses `/tmp/` SQLite (ephemeral!)
- No migration system — schema changes require dropping and recreating tables
- Data is lost on every Vercel cold start

### Proposed HLD
```
┌──────────────┐     ┌─────────────┐     ┌──────────────────┐
│   Alembic    │──▶  │  Migration  │──▶  │   PostgreSQL     │
│  (Versioned) │     │   Scripts   │     │  (Neon/Supabase) │
└──────────────┘     └─────────────┘     └──────────────────┘
```

### What You'll Learn
- **Database Migrations** with Alembic (version-controlled schema changes)
- **Connection pooling** with `pgbouncer`
- **ACID properties** in practice
- **Schema evolution** without data loss

### Implementation Notes
- Use **Neon** or **Supabase** for free serverless PostgreSQL
- Add `alembic init` and create migration scripts
- Add `POSTGRES_URL` to Vercel env vars

---

## 3. Caching Layer (Redis)

### Current Problem
Every cron hit queries the full DB to check interval timing and build the avoid list. As the problem count grows, this becomes expensive.

### Proposed HLD
```
┌──────────┐     ┌───────────┐     ┌──────────────┐
│  Flask   │──▶  │   Redis   │──▶  │  PostgreSQL  │
│   API    │     │  (Cache)  │     │  (Source of   │
└──────────┘     └───────────┘     │   Truth)      │
                  Cache-Aside      └──────────────┘
```

### What You'll Learn
- **Cache-Aside Pattern** (Lazy Loading)
- **Cache Invalidation** strategies (TTL, write-through)
- **Redis data structures** (Sets for dedup, Sorted Sets for leaderboard)
- **Cache stampede prevention**

### Implementation Notes
- Cache `all_sent_titles` as a Redis Set → O(1) dedup lookups
- Cache `last_successful_timestamp` with 5-minute TTL
- Invalidate on new problem send

---

## 4. Rate Limiting & API Security

### Current Problem
The `/api/cron` and `/api/trigger` endpoints are publicly accessible. Anyone can spam them to trigger unlimited LLM calls and emails.

### Proposed HLD
```
┌──────────────┐     ┌──────────────┐     ┌──────────┐
│   Request    │──▶  │    Rate      │──▶  │  Flask   │
│              │     │   Limiter    │     │  Route   │
└──────────────┘     │  (Token      │     └──────────┘
                     │   Bucket)    │
                     └──────────────┘
```

### What You'll Learn
- **Token Bucket** / **Sliding Window** rate limiting algorithms
- **API Key authentication** with Bearer tokens
- **HMAC signature verification** for webhook security
- **CORS hardening** (restrict allowed origins)

### Implementation Notes
- Use `flask-limiter` with Redis backend
- Add `Authorization: Bearer <secret>` header check for cron endpoints
- GitHub Actions passes the secret via `${{ secrets.CRON_API_KEY }}`

---

## 5. Observability & Monitoring

### Current Problem
No logging, no metrics, no alerts. If a cron fails silently, nobody knows.

### Proposed HLD
```
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│  Flask   │──▶  │  Structured  │──▶  │  Dashboard   │
│   App    │     │   Logging    │     │  (Grafana /   │
└──────────┘     │  (JSON logs) │     │   Vercel)     │
      │          └──────────────┘     └──────────────┘
      ▼
┌──────────────┐
│   Metrics    │
│  (Counters,  │
│  Histograms) │
└──────────────┘
```

### What You'll Learn
- **Structured logging** (JSON format with correlation IDs)
- **Metrics** (Prometheus counters: emails_sent_total, llm_latency_seconds)
- **Distributed tracing** with OpenTelemetry
- **Alerting** (PagerDuty / Slack webhook on failure)

### Implementation Notes
- Use Python's `logging` module with JSON formatter
- Add a `/api/health` endpoint for uptime monitoring
- Track: email success rate, LLM response time, dedup retry count

---

## 6. Event-Driven Architecture (Webhooks)

### Current Problem
The frontend must poll `/api/logs` to check for new problems. No real-time updates.

### Proposed HLD
```
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│  Notifier│──▶  │   Event Bus  │──▶  │  WebSocket   │
│  (sends) │     │  (pub/sub)   │     │  (Frontend)  │
└──────────┘     └──────────────┘     └──────────────┘
                       │
                       ▼
                 ┌──────────────┐
                 │   Webhook    │
                 │  (Slack/     │
                 │   Discord)   │
                 └──────────────┘
```

### What You'll Learn
- **Pub/Sub pattern** (Publishers and Subscribers)
- **WebSockets** for real-time frontend updates
- **Server-Sent Events (SSE)** as a simpler alternative
- **Webhook design** (idempotency, retry, signatures)

---

## 7. CI/CD Pipeline

### Current Problem
No automated testing on push. No staging environment. Manual deploys.

### Proposed HLD
```
┌──────────┐     ┌──────────────┐     ┌──────────┐     ┌──────────┐
│   Push   │──▶  │   GitHub     │──▶  │  Vercel  │──▶  │  Prod    │
│  to PR   │     │   Actions    │     │ Preview  │     │  Deploy  │
└──────────┘     │  (lint+test) │     │  Deploy  │     └──────────┘
                 └──────────────┘     └──────────┘
```

### What You'll Learn
- **CI/CD pipeline design** (lint → test → build → deploy)
- **Preview deployments** (Vercel creates a URL per PR)
- **Branch protection rules** (require passing tests before merge)
- **Environment variables** management (dev vs staging vs prod)

### Implementation Notes
- Add a `ci.yml` workflow that runs `pytest` and `oxlint` on every PR
- Vercel auto-deploys preview URLs for PRs (already enabled)
- Add branch protection: require CI green before merge

---

## 8. Multi-Tenant Architecture

### Current Problem
Receiver email is hardcoded. Only one user can use the system.

### Proposed HLD
```
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│   User   │──▶  │   Auth       │──▶  │  Tenant-     │
│  Login   │     │  (OAuth/JWT) │     │  Scoped DB   │
└──────────┘     └──────────────┘     └──────────────┘
```

### What You'll Learn
- **Authentication** (OAuth 2.0 with Google)
- **JWT tokens** for session management
- **Row-Level Security** (each user only sees their own data)
- **Multi-tenancy patterns** (shared DB with tenant_id column)

---

## 9. Microservices Decomposition (Advanced)

### Current Problem
Monolithic Flask app handles notifications, scheduling, analytics, and frontend serving.

### Proposed HLD
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Notification   │     │   Scheduler     │     │   Analytics     │
│   Service       │     │    Service      │     │    Service      │
│  (LLM + Email)  │     │  (Cron logic)   │     │  (Logs + Stats) │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 ▼
                          ┌──────────────┐
                          │   API        │
                          │   Gateway    │
                          └──────────────┘
```

### What You'll Learn
- **Service decomposition** (bounded contexts)
- **API Gateway pattern** (routing, auth, rate limiting)
- **Inter-service communication** (REST vs gRPC vs events)
- **Docker & Kubernetes** basics
- **Service mesh** concepts

---

## 10. Data Analytics & ML Integration

### Current Problem
No analytics on problem difficulty patterns, completion rates, or learning curves.

### Proposed HLD
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Raw Logs    │──▶  │  Analytics   │──▶  │  ML Model    │
│  (Postgres)  │     │  Pipeline    │     │  (Predict     │
└──────────────┘     └──────────────┘     │   Weakness)   │
                                          └──────────────┘
```

### What You'll Learn
- **ETL pipelines** (Extract, Transform, Load)
- **Time-series analysis** of completion patterns
- **Recommendation systems** (suggest problems based on weak topics)
- **A/B testing** (which email format gets more problems solved?)

---

## Priority Matrix

| Enhancement | Impact | Effort | Priority |
|------------|--------|--------|----------|
| PostgreSQL + Alembic | 🔴 High | 🟢 Low | **P0** |
| CI/CD Pipeline | 🔴 High | 🟢 Low | **P0** |
| Rate Limiting | 🔴 High | 🟢 Low | **P1** |
| Redis Caching | 🟠 Medium | 🟠 Medium | **P1** |
| Observability | 🟠 Medium | 🟠 Medium | **P2** |
| Message Queue | 🟠 Medium | 🔴 High | **P2** |
| Webhooks/SSE | 🟡 Low | 🟠 Medium | **P3** |
| Multi-Tenant | 🟡 Low | 🔴 High | **P3** |
| Microservices | 🟡 Low | 🔴 High | **P4** |
| ML Integration | 🟡 Low | 🔴 High | **P4** |
