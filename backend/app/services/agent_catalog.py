"""Authoritative 60-Agent Taxonomy (25 Core + 35 Extensible) for ULTRON OS 2026."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import AgentRecord

# Tuple: (agent_id, name, tier, domain, role_description, tools, permission_scope, default_reasoning_tier)
AGENT_CATALOG_60: list[tuple[str, str, str, str, str, list[str], str, int]] = [
    # --- 25 Core Specialist Agents ---
    ("AGT-01", "Executive Agent", "CORE_25", "Executive Intelligence", "Master strategic synthesis, cross-domain objective alignment, and executive escalation.", ["neon_router", "argon_dag", "memory_query"], "TIER_1_EXEC", 5),
    ("AGT-02", "Research Agent", "CORE_25", "Research", "Deep multi-source web intelligence, citation verification, and factual synthesis.", ["http_fetch_public", "gemini_analyze", "memory_query"], "TIER_2_READ", 4),
    ("AGT-03", "Coding Agent", "CORE_25", "Coding", "Full-stack Python, FastAPI, React, TypeScript, and SQL code generation.", ["gemini_analyze", "memory_query"], "TIER_2_SANDBOX", 3),
    ("AGT-04", "Debugging Agent", "CORE_25", "Debugging", "Stack-trace diagnosis, root-cause isolation, and automated regression patching.", ["gemini_analyze", "system_diagnostics"], "TIER_2_SANDBOX", 3),
    ("AGT-05", "Software Architecture Agent", "CORE_25", "Software Architecture", "System topology, serverless split-stack blueprints, and scalability engineering.", ["gemini_analyze", "memory_query"], "TIER_2_READ", 4),
    ("AGT-06", "Marketing Agent", "CORE_25", "Marketing", "Go-to-market positioning, funnel architecture, and multi-channel campaign planning.", ["gemini_analyze", "memory_query"], "TIER_2_READ", 2),
    ("AGT-07", "Sales Agent", "CORE_25", "Sales", "B2B/B2C outreach scripts, enterprise pitch structuring, and conversion optimization.", ["gemini_analyze", "memory_query"], "TIER_2_READ", 2),
    ("AGT-08", "Finance Agent", "CORE_25", "Finance", "Cash-flow modeling, unit economics, NGN/USD treasury tracking, and P&L analysis.", ["financial_transfer_request", "gemini_analyze"], "TIER_3_GATED", 4),
    ("AGT-09", "Business Strategy Agent", "CORE_25", "Business Strategy", "Competitive moats, Lagos-to-London expansion roadmaps, and operational KPIs.", ["gemini_analyze", "memory_query"], "TIER_2_READ", 4),
    ("AGT-10", "Legal Research Agent", "CORE_25", "Legal Research", "Regulatory compliance research, terms analysis, and Nigerian/UK corporate frameworks.", ["gemini_analyze", "memory_query"], "TIER_2_READ", 4),
    ("AGT-11", "Data Analysis Agent", "CORE_25", "Data Analysis", "Statistical exploration, cohort segmentation, and SQL/Pandas analytical pipelines.", ["gemini_analyze", "memory_query"], "TIER_2_READ", 3),
    ("AGT-12", "UI/UX Design Agent", "CORE_25", "UI/UX Design", "Dark-slate institutional design systems, responsive wireframes, and accessibility.", ["gemini_analyze"], "TIER_2_READ", 2),
    ("AGT-13", "Image Generation Agent", "CORE_25", "Image Generation", "Visual asset specification, brand iconography, and image generation pipelines.", ["gemini_analyze"], "TIER_2_MEDIA", 2),
    ("AGT-14", "Video Production Agent", "CORE_25", "Video Production", "Storyboard sequencing, motion direction, and video workflow orchestration.", ["gemini_analyze"], "TIER_2_MEDIA", 2),
    ("AGT-15", "Professional Writing Agent", "CORE_25", "Professional Writing", "Grant proposals, investor memos, technical documentation, and executive reports.", ["gemini_analyze", "memory_query"], "TIER_2_READ", 3),
    ("AGT-16", "Communication Agent", "CORE_25", "Communication", "Email & WhatsApp message drafting with mandatory ApprovalGate before dispatch.", ["gemini_analyze"], "TIER_3_GATED", 2),
    ("AGT-17", "Productivity Agent", "CORE_25", "Productivity", "Priority scheduling, milestone tracking, and deep-work time blocking.", ["memory_query", "gemini_analyze"], "TIER_2_READ", 2),
    ("AGT-18", "Automation Agent", "CORE_25", "Automation", "Event-driven webhooks, cron pipelines, and multi-step workflow automation.", ["system_diagnostics", "gemini_analyze"], "TIER_2_SANDBOX", 3),
    ("AGT-19", "Device Management Agent", "CORE_25", "Device Management", "Windows desktop & iPhone PWA cross-device health, telemetry, and state sync.", ["system_diagnostics"], "TIER_2_OS", 1),
    ("AGT-20", "Security Agent", "CORE_25", "Security", "Zero-trust policy enforcement, secret vault auditing, and anomaly containment.", ["system_diagnostics", "memory_query"], "TIER_1_SEC", 4),
    ("AGT-21", "Knowledge Management Agent", "CORE_25", "Knowledge Management", "Episodic/semantic memory indexing, deduplication, and knowledge graph linking.", ["memory_query", "gemini_analyze"], "TIER_2_MEM", 2),
    ("AGT-22", "Customer Support Agent", "CORE_25", "Customer Support", "Caravan user onboarding, ticket triage, and structured resolution playbooks.", ["memory_query", "gemini_analyze"], "TIER_2_READ", 2),
    ("AGT-23", "Analytics Agent", "CORE_25", "Analytics", "Funnel conversion telemetry, retention cohorts, and executive KPI scorecards.", ["memory_query", "gemini_analyze"], "TIER_2_READ", 3),
    ("AGT-24", "3D Modelling Agent", "CORE_25", "3D Modelling", "Three.js/WebGL scene geometry, spatial assets, and interactive 3D visualization.", ["gemini_analyze"], "TIER_2_MEDIA", 2),
    ("AGT-25", "Testing Agent", "CORE_25", "Testing", "Unit, integration, security, and regression verification suites with honest reporting.", ["system_diagnostics", "gemini_analyze"], "TIER_2_SANDBOX", 3),
    # --- 35 Extensible Specialist Agents ---
    ("AGT-26", "Product Management Agent", "EXTENSIBLE_35", "Product Management", "PRDs, user stories, backlog prioritization, and release readiness criteria.", ["gemini_analyze", "memory_query"], "TIER_2_READ", 3),
    ("AGT-27", "Project Management Agent", "EXTENSIBLE_35", "Project Management", "Critical-path scheduling, dependency tracking, and stage-gate delivery.", ["memory_query", "gemini_analyze"], "TIER_2_READ", 2),
    ("AGT-28", "Database Engineering Agent", "EXTENSIBLE_35", "Database Engineering", "SQLite WAL, PostgreSQL/Supabase schemas, migrations, and query optimization.", ["system_diagnostics", "gemini_analyze"], "TIER_2_SANDBOX", 3),
    ("AGT-29", "API Engineering Agent", "EXTENSIBLE_35", "API Engineering", "REST/WebSocket contract design, OpenAPI specs, and rate-limited endpoints.", ["gemini_analyze"], "TIER_2_SANDBOX", 3),
    ("AGT-30", "Cloud Infrastructure Agent", "EXTENSIBLE_35", "Cloud Infrastructure", "Supabase, Vercel, and Cloudflare edge deployment topologies.", ["system_diagnostics", "gemini_analyze"], "TIER_2_INFRA", 3),
    ("AGT-31", "DevOps Agent", "EXTENSIBLE_35", "DevOps", "CI/CD pipelines, container builds, health probes, and automated rollback scripts.", ["system_diagnostics", "gemini_analyze"], "TIER_2_INFRA", 3),
    ("AGT-32", "Quality Assurance Agent", "EXTENSIBLE_35", "Quality Assurance", "End-to-end acceptance verification and zero-mock integrity audits.", ["system_diagnostics", "gemini_analyze"], "TIER_2_SANDBOX", 3),
    ("AGT-33", "Cybersecurity Analysis Agent", "EXTENSIBLE_35", "Cybersecurity Analysis", "Threat modeling, OWASP Top 10 hardening, SSRF/XSS/SQLi defense validation.", ["system_diagnostics", "gemini_analyze"], "TIER_1_SEC", 4),
    ("AGT-34", "Documentation Agent", "EXTENSIBLE_35", "Documentation", "Architecture blueprints, API reference manuals, and operator runbooks.", ["gemini_analyze", "memory_query"], "TIER_2_READ", 2),
    ("AGT-35", "Market Intelligence Agent", "EXTENSIBLE_35", "Market Intelligence", "TAM/SAM/SOM sizing across Nigerian and UK technology and funding ecosystems.", ["http_fetch_public", "gemini_analyze"], "TIER_2_READ", 4),
    ("AGT-36", "Competitor Intelligence Agent", "EXTENSIBLE_35", "Competitor Intelligence", "Feature benchmarking, pricing teardowns, and strategic differentiation.", ["http_fetch_public", "gemini_analyze"], "TIER_2_READ", 3),
    ("AGT-37", "Customer Acquisition Agent", "EXTENSIBLE_35", "Customer Acquisition", "CAC optimization, partner channels, and high-intent founder acquisition loops.", ["gemini_analyze"], "TIER_2_READ", 2),
    ("AGT-38", "Customer Retention Agent", "EXTENSIBLE_35", "Customer Retention", "Churn prediction, lifecycle nudges, and grant-alert engagement workflows.", ["gemini_analyze"], "TIER_2_READ", 2),
    ("AGT-39", "Advertising Strategy Agent", "EXTENSIBLE_35", "Advertising Strategy", "Paid acquisition targeting, creative testing matrices, and ROAS guardrails.", ["gemini_analyze"], "TIER_2_READ", 2),
    ("AGT-40", "Content Strategy Agent", "EXTENSIBLE_35", "Content Strategy", "Editorial pillars, founder education guides, and authority distribution.", ["gemini_analyze"], "TIER_2_READ", 2),
    ("AGT-41", "Social Media Agent", "EXTENSIBLE_35", "Social Media", "Platform-native threads, launch announcements, and community engagement.", ["gemini_analyze"], "TIER_2_READ", 1),
    ("AGT-42", "Branding Agent", "EXTENSIBLE_35", "Branding", "Institutional identity systems, voice guidelines, and visual positioning.", ["gemini_analyze"], "TIER_2_READ", 2),
    ("AGT-43", "Graphic Design Agent", "EXTENSIBLE_35", "Graphic Design", "Layout grids, typography hierarchy, and high-contrast visual assets.", ["gemini_analyze"], "TIER_2_MEDIA", 2),
    ("AGT-44", "Presentation Creation Agent", "EXTENSIBLE_35", "Presentation Creation", "Investor pitch decks, board briefings, and structured narrative slides.", ["gemini_analyze"], "TIER_2_READ", 3),
    ("AGT-45", "Audio Processing Agent", "EXTENSIBLE_35", "Audio Processing", "Audio cleanup, diarization structuring, and meeting summary extraction.", ["gemini_analyze"], "TIER_2_MEDIA", 2),
    ("AGT-46", "Voice Engineering Agent", "EXTENSIBLE_35", "Voice Engineering", "Wake-word pipeline, low-latency TTS/STT routing, and voice command parsing.", ["gemini_analyze"], "TIER_2_MEDIA", 1),
    ("AGT-47", "Video Analysis Agent", "EXTENSIBLE_35", "Video Analysis", "Frame-level summarization, visual event extraction, and media indexing.", ["gemini_analyze"], "TIER_2_MEDIA", 2),
    ("AGT-48", "Data Engineering Agent", "EXTENSIBLE_35", "Data Engineering", "ETL collectors, schema validation, and 81-collector ingestion normalization.", ["gemini_analyze", "system_diagnostics"], "TIER_2_SANDBOX", 3),
    ("AGT-49", "Predictive Analytics Agent", "EXTENSIBLE_35", "Predictive Analytics", "Time-series revenue projections, grant win-probability scoring, and burn alerts.", ["gemini_analyze"], "TIER_2_READ", 4),
    ("AGT-50", "Scientific Research Agent", "EXTENSIBLE_35", "Scientific Research", "Hypothesis formulation, peer-reviewed literature synthesis, and methodology review.", ["http_fetch_public", "gemini_analyze"], "TIER_2_READ", 4),
    ("AGT-51", "Mathematics Agent", "EXTENSIBLE_35", "Mathematics", "Symbolic/numerical verification, optimization modeling, and statistical proofs.", ["gemini_analyze"], "TIER_2_READ", 4),
    ("AGT-52", "Education & Tutoring Agent", "EXTENSIBLE_35", "Education & Tutoring", "First-principles technical breakdowns, step-by-step study plans, and drills.", ["gemini_analyze"], "TIER_2_READ", 2),
    ("AGT-53", "Human Resources Agent", "EXTENSIBLE_35", "Human Resources", "Role scorecards, technical hiring rubrics, and contractor onboarding.", ["gemini_analyze"], "TIER_2_READ", 2),
    ("AGT-54", "Operations Management Agent", "EXTENSIBLE_35", "Operations Management", "SOP standardization, bottleneck elimination, and cross-team SLA tracking.", ["gemini_analyze", "memory_query"], "TIER_2_READ", 3),
    ("AGT-55", "Supply Chain Analysis Agent", "EXTENSIBLE_35", "Supply Chain Analysis", "Vendor evaluation, hardware procurement logistics, and cost-landed modeling.", ["gemini_analyze"], "TIER_2_READ", 3),
    ("AGT-56", "Funding Research Agent", "EXTENSIBLE_35", "Funding Research", "Caravan grant, accelerator, angel, and non-dilutive capital discovery (NG & UK).", ["http_fetch_public", "gemini_analyze"], "TIER_2_READ", 4),
    ("AGT-57", "Investment Analysis Agent", "EXTENSIBLE_35", "Investment Analysis", "Valuation modeling, cap-table dilution simulation, and treasury yield comparison.", ["financial_transfer_request", "gemini_analyze"], "TIER_3_GATED", 4),
    ("AGT-58", "Compliance Monitoring Agent", "EXTENSIBLE_35", "Compliance Monitoring", "Continuous policy verification, audit-chain validation, and regulatory alerts.", ["system_diagnostics", "gemini_analyze"], "TIER_1_SEC", 4),
    ("AGT-59", "System Diagnostics Agent", "EXTENSIBLE_35", "System Diagnostics", "Live latency profiling, database health, and provider failover diagnostics.", ["system_diagnostics"], "TIER_2_INFRA", 1),
    ("AGT-60", "Agent Development & Evaluation Agent", "EXTENSIBLE_35", "Agent Development & Evaluation", "Controlled agent capability registration, benchmark scoring, and rollback safety.", ["system_diagnostics", "gemini_analyze"], "TIER_1_EXEC", 5),
]


def seed_agent_catalog(db: Session) -> int:
    """Seed all 60 specialist agents idempotently into the agents table."""
    inserted = 0
    now = datetime.now(timezone.utc)
    for aid, name, tier, domain, desc, tools, perm, reasoning_tier in AGENT_CATALOG_60:
        existing = db.get(AgentRecord, aid)
        if existing is not None:
            continue
        sys_inst = (
            f"You are {name} ({aid}) within ULTRON OS 2026. Domain: {domain}. {desc} "
            f"Operate strictly within permission scope {perm}, respect tenant boundaries, "
            "and never fabricate telemetry or bypass ApprovalGate."
        )
        db.add(
            AgentRecord(
                agent_id=aid,
                name=name,
                tier=tier,
                domain=domain,
                role_description=desc,
                system_instruction=sys_inst,
                tools_json=json.dumps(tools),
                permission_scope=perm,
                capability_state="AVAILABLE",
                default_reasoning_tier=reasoning_tier,
                tasks_completed=0,
                last_active=now,
            )
        )
        inserted += 1
    db.flush()
    return inserted
