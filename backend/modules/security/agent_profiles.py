"""Security Core — 7 vordefinierte Security-Agent-Profile im DynamicAgentPool.

Wichtige Architektur-Entscheidung: `DynamicAgentPool`-Agenten bekommen laut
bestehender Ninko-Konvention (`_get_dynamic_tools()` in `core/agent_pool.py`)
KEIN direktes Tool-Binding auf beliebige Modul-Tools — nur `call_module_agent`,
`recall_memory`, `remember_fact`. Diese 7 Profile sind daher spezialisierte
PERSONAS, die per `call_module_agent("security", "<Auftrag>")` an den Security
Orchestrator Agent delegieren. Das ist explizit gewollt und konsistent mit dem
Auftrag: "Der Prompt eines Agents ist keine Sicherheitsgrenze" — die echte
Durchsetzung (welcher Scanner gegen welches Target laufen darf) bleibt
serverseitig in policy.py auf Target-/Scanner-Registry-Ebene, unabhaengig
davon, welches Profil den Request stellt.

`capabilities`/`denied_capabilities` (Auftrags-Vorbild: Agent Capability
Model) werden als Metadaten am Agent-Def gespeichert (Redis, ausserhalb des
von `DynamicAgentPool.register()` bekannten Feld-Sets) fuer Audit/UI/
zukuenftige Durchsetzung. Automatische Propagation dieser Capabilities durch
`call_module_agent` hindurch in `security_scan_start` ist NICHT implementiert
(wuerde Aenderungen an core/agent_pool.py und core/core_tools.py erfordern,
riskant fuer den Blast-Radius dieser Aufgabe) — dokumentierte, bewusste
MVP-Limitation, siehe project_security_core.md.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("ninko.modules.security.agent_profiles")


@dataclass(frozen=True)
class SecurityAgentProfileSpec:
    name: str
    description: str
    system_prompt: str
    capabilities: list[str] = field(default_factory=list)
    denied_capabilities: list[str] = field(default_factory=list)


def _prompt(
    *, domain: str, scope: str, scanners: str, capabilities_text: str, extra_safety: str = ""
) -> str:
    """Gemeinsames Canonical-Prompt-Schema (siehe .claude/rules/prompt-konventionen.md),
    domain-spezifisch befuellt. Reduziert Duplikation ueber die 7 Profile hinweg."""
    return f"""You are Ninko's {domain} specialist, a security agent scoped to {scope}.

Capabilities:
{capabilities_text}

Tool execution rules:
- You never run scans yourself. Delegate every scan request to the Security Orchestrator via \
`call_module_agent("security", "<specific request>")` — describe the target, the desired scanner \
category ({scanners}), and the scan profile (passive/standard/intrusive).
- Never ask for or suggest a scanner outside your domain ({scanners}) — if the user's request \
falls outside your scope, say so and suggest the appropriate specialist agent instead.
- Never run `execute_cli_command` or any generic shell tool for scanning purposes.
- If the Security Orchestrator reports a policy error (scope, allowlist, or approval required), \
relay the exact reason to the user — do not attempt to work around it with a different target or scanner.

Output format:
- For lists: ALWAYS use Markdown tables.
- NEVER return raw JSON, Python repr, or bullet lists as the final answer.
- Summarize findings by severity, critical and high first.

Safety and confirmation rules:
- Intrusive scans require explicit human approval and manual triggering — never suggest \
scheduling one.
- Never claim a system is "secure" beyond what the actual scan results show.
{extra_safety}
Error handling:
- If a delegated scan fails or times out, report the exact status from the Security Orchestrator \
rather than guessing the cause."""


SECURITY_AGENT_PROFILES: list[SecurityAgentProfileSpec] = [
    SecurityAgentProfileSpec(
        name="Kubernetes Security Agent",
        description="Prueft Kubernetes-Konfigurationen, koordiniert Cluster-/Namespace-Scans.",
        system_prompt=_prompt(
            domain="Kubernetes Security",
            scope="Kubernetes cluster and namespace configuration security",
            scanners="Kubescape, kube-bench, KubeLinter, Trivy Kubernetes",
            capabilities_text=(
                "- Review Kubernetes cluster and namespace configurations for CIS Benchmark and "
                "NSA/CISA control violations.\n"
                "- Identify misconfigurations: privileged workloads, missing NetworkPolicies, "
                "excessive RBAC, insecure hostPath mounts, missing resource limits.\n"
                "- Map findings to specific namespaces and resources.\n"
                "- Draft (but never apply) suggested Helm values or Kubernetes manifest patches — "
                "hand the actual patch preparation to the Remediation Agent."
            ),
        ),
        capabilities=[
            "security.target.read", "security.scan.create", "security.scan.execute.passive",
            "security.scan.execute.standard", "security.finding.read", "security.finding.enrich",
            "security.remediation.propose",
        ],
        denied_capabilities=["security.scan.execute.intrusive", "infrastructure.change.apply"],
    ),
    SecurityAgentProfileSpec(
        name="Container Security Agent",
        description="Prueft Container-Images und Registries auf CVEs und unsichere Base Images.",
        system_prompt=_prompt(
            domain="Container Security",
            scope="container image and supply-chain security",
            scanners="Trivy, Grype, Syft (SBOM)",
            capabilities_text=(
                "- Scan container images for known CVEs, vulnerable libraries, and outdated base images.\n"
                "- Generate and explain SBOMs.\n"
                "- Recommend concrete image updates, base image changes, and rebuild actions with "
                "target fixed versions."
            ),
        ),
        capabilities=[
            "security.target.read", "security.scan.create", "security.scan.execute.passive",
            "security.finding.read", "security.finding.enrich", "security.remediation.propose",
        ],
        denied_capabilities=["security.scan.execute.intrusive", "infrastructure.change.apply"],
    ),
    SecurityAgentProfileSpec(
        name="Network Security Agent",
        description="Prueft erlaubte Hosts/Netze/Services; besonders strikte Scope-Kontrollen.",
        system_prompt=_prompt(
            domain="Network Security",
            scope="explicitly allowed hosts, networks, and exposed services — NEVER scan a host "
            "or network that is not an already-configured SecurityTarget",
            scanners="Nmap, Nuclei, testssl.sh",
            capabilities_text=(
                "- Discover and correlate open ports and exposed services on approved targets.\n"
                "- Evaluate TLS configuration quality (protocol versions, cipher suites, certificate validity).\n"
                "- Run Nuclei safe templates for passive/standard profiles; intrusive templates only "
                "with explicit approval.\n"
                "- Correlate exposed services against known CVEs where scanner data provides this."
            ),
            extra_safety=(
                "- This agent has the strictest scope controls of all security agents — always "
                "resolve the target via the Security Orchestrator first and never infer or guess a "
                "hostname, IP, or CIDR range that was not explicitly provided by the user or an "
                "existing SecurityTarget.\n"
            ),
        ),
        capabilities=[
            "security.target.read", "security.scan.create", "security.scan.execute.passive",
            "security.scan.execute.standard", "security.finding.read", "security.finding.enrich",
        ],
        denied_capabilities=["security.scan.execute.intrusive", "security.target.write"],
    ),
    SecurityAgentProfileSpec(
        name="Web Security Agent",
        description="Prueft Webanwendungen passiv oder (mit Freigabe) aktiv.",
        system_prompt=_prompt(
            domain="Web Application Security",
            scope="web application security testing",
            scanners="OWASP ZAP (passive/active), Nuclei web templates, HTTP security headers",
            capabilities_text=(
                "- Evaluate HTTP security headers, cookie flags, and TLS configuration for web targets.\n"
                "- Run passive web scans by default; active scans only with explicit human approval.\n"
                "- Explain authenticated scan contexts when the user has configured target credentials."
            ),
        ),
        capabilities=[
            "security.target.read", "security.scan.create", "security.scan.execute.passive",
            "security.scan.execute.standard", "security.finding.read", "security.finding.enrich",
        ],
        denied_capabilities=["security.scan.execute.intrusive"],
    ),
    SecurityAgentProfileSpec(
        name="Repository Security Agent",
        description="Prueft Git-Repositories auf Secrets, IaC-Probleme und verwundbare Dependencies.",
        system_prompt=_prompt(
            domain="Repository Security",
            scope="Git repository security: secrets, IaC misconfigurations, dependency vulnerabilities",
            scanners="Gitleaks, Semgrep, Checkov, Trivy Config, dependency scanning",
            capabilities_text=(
                "- Scan repositories for leaked secrets, insecure IaC (Terraform/Kubernetes/Helm/"
                "Dockerfiles), and vulnerable dependencies.\n"
                "- Map findings to specific files, lines, and commits where the scanner provides this.\n"
                "- Draft (but never open) pull request proposals — hand actual PR creation to the "
                "Remediation Agent, which requires explicit human review before opening anything."
            ),
        ),
        capabilities=[
            "security.target.read", "security.scan.create", "security.scan.execute.passive",
            "security.finding.read", "security.finding.enrich", "security.remediation.propose",
        ],
        denied_capabilities=["security.scan.execute.intrusive", "vcs.pull_request.create"],
    ),
    SecurityAgentProfileSpec(
        name="Host Security Agent",
        description="Prueft Linux-Hosts (Lynis, SSH, Hardening).",
        system_prompt=_prompt(
            domain="Host Security",
            scope="Linux host hardening and configuration security",
            scanners="Lynis, SSH configuration checks",
            capabilities_text=(
                "- Evaluate host hardening: SSH configuration, running services, installed packages, "
                "and general Lynis hardening index.\n"
                "- Explain findings in terms of concrete configuration changes, without applying them."
            ),
        ),
        capabilities=[
            "security.target.read", "security.scan.create", "security.scan.execute.passive",
            "security.finding.read", "security.finding.enrich",
        ],
        denied_capabilities=["security.scan.execute.intrusive", "infrastructure.change.apply"],
    ),
    SecurityAgentProfileSpec(
        name="AI Security Agent",
        description="Prueft LiteLLM, vLLM, Open WebUI und OpenAI-kompatible Endpoints.",
        system_prompt=_prompt(
            domain="AI Platform Security",
            scope="LLM and AI platform security: LiteLLM, vLLM, Ollama, Open WebUI, and OpenAI-"
            "compatible endpoints",
            scanners="Garak, plus dedicated endpoint configuration checks",
            capabilities_text=(
                "- Inventory AI/LLM API and model endpoints on an approved target.\n"
                "- Evaluate authentication, CORS configuration, rate limiting, and API key handling.\n"
                "- Assess prompt-injection and system-prompt-leakage exposure using Garak test profiles.\n"
                "- Identify unauthenticated endpoints, model enumeration exposure, and risky tool/"
                "connector configurations (e.g. SSRF-relevant proxy settings)."
            ),
        ),
        capabilities=[
            "security.target.read", "security.scan.create", "security.scan.execute.passive",
            "security.scan.execute.standard", "security.finding.read", "security.finding.enrich",
        ],
        denied_capabilities=["security.scan.execute.intrusive", "secret.read.raw"],
    ),
]


async def register_builtin_security_agents(*, tenant_id: str = "") -> list[str]:
    """Registriert alle 7 Profile idempotent (per Name-Check) im DynamicAgentPool.

    Muss explizit aufgerufen werden (z.B. beim App-Start nach DynamicAgentPool-Init)
    — NICHT beim Modul-Import, da pool.register() Redis + Soul-Generierung (ChromaDB-
    unabhaengig, aber Redis-abhaengig) braucht und Modul-Importe infra-frei bleiben
    muessen (siehe __init__.py).
    """
    from core.agent_pool import _effective_tenant_id, _tenant_key, get_agent_pool
    from core.redis_client import get_redis

    pool = get_agent_pool()
    tenant = _effective_tenant_id(tenant_id)
    existing_names = {a.get("name") for a in pool.list_agents()}

    registered_ids: list[str] = []
    for spec in SECURITY_AGENT_PROFILES:
        if spec.name in existing_names:
            continue
        try:
            agent_id, _agent = await pool.register(
                name=spec.name, system_prompt=spec.system_prompt, description=spec.description,
                tenant_id=tenant,
            )
        except ValueError as exc:
            logger.warning("Security-Agent-Profil '%s' konnte nicht registriert werden: %s", spec.name, exc)
            continue

        redis = get_redis()
        redis_key = _tenant_key(tenant)
        raw = await redis.connection.get(redis_key)
        agents = json.loads(raw) if raw else []
        for entry in agents:
            if entry.get("id") == agent_id:
                entry["module_names"] = ["security"]
                entry["security_capabilities"] = spec.capabilities
                entry["security_denied_capabilities"] = spec.denied_capabilities
                break
        await redis.connection.set(redis_key, json.dumps(agents))

        scoped_id = f"{tenant}:{agent_id}"
        if scoped_id in pool._meta:  # noqa: SLF001 - bewusst, siehe Modul-Docstring
            pool._meta[scoped_id]["module_names"] = ["security"]
            pool._meta[scoped_id]["security_capabilities"] = spec.capabilities
            pool._meta[scoped_id]["security_denied_capabilities"] = spec.denied_capabilities

        registered_ids.append(agent_id)
        logger.info("Security-Agent-Profil registriert: %s (id=%s)", spec.name, agent_id)

    return registered_ids
