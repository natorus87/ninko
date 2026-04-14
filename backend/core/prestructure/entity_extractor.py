"""Entity extraction for systems, services, namespaces, and resources."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

from core.prestructure.schemas import ScopeEntities, Domain
from core.prestructure.normalizer import NormalizedInput


class EntityExtractor:
    """
    Extract entities from normalized input using regex and keyword matching.

    Recognizes systems, services, hosts, namespaces, clusters, resources,
    and time references without LLM calls.
    """

    # Known system keywords
    SYSTEM_KEYWORDS: Dict[str, List[str]] = {
        "kubernetes": [
            "kubernetes",
            "k8s",
            "cluster",
            "pod",
            "pods",
            "deployment",
            "service",
            "ingress",
        ],
        "gitlab": ["gitlab", "git-lab", "git lab"],
        "github": ["github", "git-hub", "git hub"],
        "proxmox": ["proxmox", "pve"],
        "docker": ["docker", "container", "containers"],
        "postgresql": ["postgres", "postgresql", "psql"],
        "mysql": ["mysql", "mariadb", "maria-db"],
        "redis": ["redis"],
        "traefik": ["traefik"],
        "nginx": ["nginx"],
        "pihole": ["pihole", "pi-hole", "pi hole"],
        "fritzbox": ["fritzbox", "fritz", "fritz!box"],
        "checkmk": ["checkmk", "check-mk"],
        "glpi": ["glpi"],
        "jira": ["jira"],
        "confluence": ["confluence"],
        "homeassistant": ["homeassistant", "home-assistant"],
        "nextcloud": ["nextcloud", "next-cloud"],
        "wordpress": ["wordpress", "word-press"],
    }

    # Resource types
    RESOURCE_KEYWORDS: List[str] = [
        "pod",
        "pods",
        "deployment",
        "deployments",
        "service",
        "services",
        "ingress",
        "ingresses",
        "configmap",
        "configmaps",
        "secret",
        "secrets",
        "node",
        "nodes",
        "namespace",
        "namespaces",
        "pvc",
        "pv",
        "persistentvolume",
        "persistentvolumes",
        "job",
        "jobs",
        "cronjob",
        "cronjobs",
        "daemonset",
        "daemonsets",
        "statefulset",
        "statefulsets",
        "replicaset",
        "replicasets",
        "pipeline",
        "pipelines",
        "runner",
        "runners",
        "repository",
        "repositories",
        "repo",
        "repos",
        "issue",
        "issues",
        "mr",
        "merge request",
        "merge requests",
        "pr",
        "pull request",
        "pull requests",
        "vm",
        "vms",
        "virtual machine",
        "virtual machines",
        "lxc",
        "container",
        "containers",
        "backup",
        "backups",
        "snapshot",
        "snapshots",
    ]

    # Time reference patterns
    TIME_PATTERNS: List[str] = [
        r"seit\s+\w+",
        r"vor\s+\d+\s+\w+",
        r"nach\s+\w+",
        r"in\s+den\s+letzten\s+\w+",
        r"die\s+letzten\s+\w+",
        r"aktuell",
        r"gerade",
        r"jetzt",
        r"heute",
        r"gestern",
        r"morgen",
        r"seit\s+gestern",
        r"seit\s+heute",
        r"in\s+der\s+letzten\s+stunde",
        r"in\s+den\s+letzten\s+\d+\s+(minuten|stunden|tagen|wochen)",
    ]

    # Pattern matchers for specific entity types
    NAMESPACE_PATTERN = re.compile(r"namespace\s+(\S+)", re.IGNORECASE)
    CLUSTER_PATTERN = re.compile(r"cluster\s+(\S+)", re.IGNORECASE)
    HOST_PATTERN = re.compile(r"(?:host|server|node)\s+(\S+)", re.IGNORECASE)

    def extract(self, normalized: NormalizedInput) -> ScopeEntities:
        """Extract all entity types from normalized input."""
        normalized_text = normalized.normalized
        tokens = normalized.tokens

        systems = self._extract_systems(normalized_text, tokens)
        services = self._extract_services(normalized_text, tokens)
        hosts = self._extract_hosts(normalized_text)
        namespaces = self._extract_namespaces(normalized_text)
        clusters = self._extract_clusters(normalized_text)
        resources = self._extract_resources(normalized_text, tokens)
        time_refs = self._extract_time_refs(normalized_text)

        return ScopeEntities(
            systems=systems,
            services=services,
            hosts=hosts,
            namespaces=namespaces,
            clusters=clusters,
            resources=resources,
            time_refs=time_refs,
        )

    def extract_domain(self, entities: ScopeEntities) -> Domain:
        """Determine domain based on extracted entities."""
        if "kubernetes" in entities.systems or entities.clusters or entities.namespaces:
            return "kubernetes"
        if "gitlab" in entities.systems or "github" in entities.systems:
            return "gitlab"
        if (
            "postgresql" in entities.systems
            or "mysql" in entities.systems
            or "redis" in entities.systems
        ):
            return "database"
        if entities.systems:
            return "infra"
        if entities.hosts or entities.services:
            return "network"
        return "unknown"

    def _extract_systems(self, normalized_text: str, tokens: List[str]) -> List[str]:
        """Extract system names from text."""
        found_systems: Set[str] = set()

        for system, keywords in self.SYSTEM_KEYWORDS.items():
            for keyword in keywords:
                if keyword in normalized_text:
                    found_systems.add(system)
                    break

        return sorted(found_systems)

    def _extract_services(self, normalized_text: str, tokens: List[str]) -> List[str]:
        """Extract service names from text."""
        found_services: Set[str] = set()

        service_indicators = [
            "postgresql",
            "postgres",
            "mysql",
            "redis",
            "traefik",
            "nginx",
            "pihole",
        ]

        for indicator in service_indicators:
            if indicator in normalized_text:
                found_services.add(indicator)

        return sorted(found_services)

    def _extract_hosts(self, normalized_text: str) -> List[str]:
        """Extract host names/IPs from text."""
        hosts: List[str] = []

        # Match explicit host mentions
        matches = self.HOST_PATTERN.findall(normalized_text)
        hosts.extend(matches)

        # Match IP addresses
        ip_pattern = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        hosts.extend(ip_pattern.findall(normalized_text))

        return hosts

    def _extract_namespaces(self, normalized_text: str) -> List[str]:
        """Extract Kubernetes namespace names."""
        namespaces: List[str] = []

        # Match "namespace X" or "im Namespace X"
        matches = self.NAMESPACE_PATTERN.findall(normalized_text)
        namespaces.extend(matches)

        # Also check for "im Namespace X" pattern
        im_ns_pattern = re.compile(r"im\s+namespace\s+(\S+)", re.IGNORECASE)
        namespaces.extend(im_ns_pattern.findall(normalized_text))

        # Filter out common non-namespace words
        exclude = {"the", "a", "an", "oder", "und", "cluster", "pod", "deployment"}
        return [ns for ns in namespaces if ns.lower() not in exclude]

    def _extract_clusters(self, normalized_text: str) -> List[str]:
        """Extract cluster names."""
        clusters: List[str] = []

        # Match "cluster X" patterns
        matches = self.CLUSTER_PATTERN.findall(normalized_text)
        clusters.extend(matches)

        # Match common cluster name patterns (e.g., prod-eu, staging-us)
        cluster_name_pattern = re.compile(
            r"\b(?:prod|staging|dev|test)[\-\_]?\w*\b", re.IGNORECASE
        )
        clusters.extend(
            [m.group(0) for m in cluster_name_pattern.finditer(normalized_text)]
        )

        return clusters

    def _extract_resources(self, normalized_text: str, tokens: List[str]) -> List[str]:
        """Extract resource types."""
        found_resources: Set[str] = set()

        for resource in self.RESOURCE_KEYWORDS:
            if resource in normalized_text:
                found_resources.add(resource)

        return sorted(found_resources)

    def _extract_time_refs(self, normalized_text: str) -> List[str]:
        """Extract time references from text."""
        time_refs: List[str] = []

        for pattern in self.TIME_PATTERNS:
            matches = re.findall(pattern, normalized_text, re.IGNORECASE)
            time_refs.extend(matches)

        return time_refs


def extract_entities(normalized: NormalizedInput) -> ScopeEntities:
    """Convenience function for entity extraction."""
    extractor = EntityExtractor()
    return extractor.extract(normalized)


def extract_domain(entities: ScopeEntities) -> Domain:
    """Convenience function for domain detection."""
    extractor = EntityExtractor()
    return extractor.extract_domain(entities)
