"""Security Core — K8sJobExecutor: isolierte Scan-Ausfuehrung als Kubernetes Job.

Jeder Scan laeuft als eigener, kurzlebiger Kubernetes-Job im dedizierten
Namespace `ninko-security` (siehe k8s/security/). Getrennt vom bestehenden
`kubernetes`-Modul (das beliebige, vom Nutzer konfigurierte Cluster verwaltet):
dieser Executor authentifiziert sich mit der EIGENEN Backend-Pod-Identitaet
(in-cluster ServiceAccount "ninko", mit einer schmalen, auf `ninko-security`
begrenzten Role — siehe k8s/security/rbac.yaml) oder, ausserhalb eines
Clusters (lokale Entwicklung), ueber die aktuelle kubeconfig.

WICHTIGER HINWEIS (bekanntes, separates Risiko, siehe
.claude/memory/project_security_core.md): Auf dem aktuell verwendeten
Cluster wurde eine RBAC-Fehlkonfiguration entdeckt (Authorization scheint
nicht durchgesetzt zu werden — jedes gueltige Token kann alles). Der Code
hier implementiert Least-Privilege korrekt; die tatsaechliche Isolation
haengt zusaetzlich davon ab, dass der Cluster RBAC durchsetzt.

Ausfuehrung: Job erstellen -> auf Terminierung warten (Timeout ueber
activeDeadlineSeconds + eigener Poll-Timeout) -> Pod-Logs als Ergebnis lesen
(Output-Size-Limit) -> Job+Pods+NetworkPolicy aufraeumen.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client.rest import ApiException

from .scanner_adapter import ExecutionSpec, ScannerExecutionResult

logger = logging.getLogger("ninko.modules.security.executor")

SECURITY_SCAN_NAMESPACE = "ninko-security"
DEFAULT_SERVICE_ACCOUNT = "ninko-security-scanner"
_POLL_INTERVAL_S = 2.0
_JOB_NAME_RE = re.compile(r"[^a-z0-9-]")


class ScanExecutionError(RuntimeError):
    """Job konnte nicht erstellt oder ausgefuehrt werden (Infrastruktur-Fehler)."""


class ScanTimeoutError(ScanExecutionError):
    """Job hat sein Timeout ueberschritten und wurde abgebrochen."""


def _sanitize_job_name(scanner_id: str, scan_run_id: str) -> str:
    """Baut einen DNS-1123-konformen Job-Namen (max 63 Zeichen)."""
    base = f"scan-{scanner_id}-{scan_run_id[:8]}".lower()
    base = _JOB_NAME_RE.sub("-", base).strip("-")
    suffix = uuid.uuid4().hex[:6]
    name = f"{base}-{suffix}"
    return name[:63].rstrip("-")


class K8sJobExecutor:
    """Fuehrt SecurityScannerAdapter-Ausfuehrungen als isolierte K8s-Jobs aus."""

    def __init__(self, *, namespace: str = SECURITY_SCAN_NAMESPACE) -> None:
        self.namespace = namespace
        self._batch_api: k8s_client.BatchV1Api | None = None
        self._core_api: k8s_client.CoreV1Api | None = None
        self._networking_api: k8s_client.NetworkingV1Api | None = None

    def _ensure_clients(self) -> None:
        if self._batch_api is not None:
            return
        try:
            k8s_config.load_incluster_config()
            logger.info("K8sJobExecutor: in-cluster Konfiguration geladen")
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()
            logger.info("K8sJobExecutor: lokale kubeconfig geladen (out-of-cluster)")
        self._batch_api = k8s_client.BatchV1Api()
        self._core_api = k8s_client.CoreV1Api()
        self._networking_api = k8s_client.NetworkingV1Api()

    # ── Manifest-Bau ──────────────────────────────────────────────────

    def _build_job_manifest(self, spec: ExecutionSpec, job_name: str, scan_run_id: str) -> k8s_client.V1Job:
        spec.assert_no_shell_string()

        env_vars = [k8s_client.V1EnvVar(name=k, value=v) for k, v in spec.env.items()]

        volume_mounts = [k8s_client.V1VolumeMount(name="tmp", mount_path="/tmp")]
        volumes = [k8s_client.V1Volume(name="tmp", empty_dir=k8s_client.V1EmptyDirVolumeSource())]
        for i, vol in enumerate(spec.volumes):
            vol_name = f"vol-{i}"
            volume_mounts.append(
                k8s_client.V1VolumeMount(name=vol_name, mount_path=vol.mount_path, read_only=vol.read_only)
            )
            volumes.append(k8s_client.V1Volume(name=vol_name, empty_dir=k8s_client.V1EmptyDirVolumeSource()))

        # Secret-Refs: jeder Eintrag ist der Name eines bereits im Cluster existierenden
        # K8s-Secrets (z.B. Kubeconfig fuer Kubescape, Access-Token fuer privaten Git-Clone),
        # read-only unter /secrets/<name> gemountet. Ninko legt diese Secrets NICHT selbst
        # an (kein Vault-Sync in dieser Phase) — Administratoren muessen sie vorab im
        # ninko-security-Namespace anlegen. Dokumentierte MVP-Limitation.
        secret_mounts = []
        for secret_name in spec.secret_refs:
            vol_name = f"secret-{secret_name}"[:63]
            volumes.append(k8s_client.V1Volume(
                name=vol_name, secret=k8s_client.V1SecretVolumeSource(secret_name=secret_name)
            ))
            secret_mounts.append(
                k8s_client.V1VolumeMount(name=vol_name, mount_path=f"/secrets/{secret_name}", read_only=True)
            )
        volume_mounts.extend(secret_mounts)

        # Workspace-Volume: geteilt zwischen Init-Containern (z.B. Git-Checkout) und dem
        # Hauptcontainer, nur angelegt wenn tatsaechlich Init-Container definiert sind.
        init_containers: list[k8s_client.V1Container] = []
        if spec.init_containers:
            volumes.append(
                k8s_client.V1Volume(name="workspace", empty_dir=k8s_client.V1EmptyDirVolumeSource())
            )
            workspace_mount = k8s_client.V1VolumeMount(name="workspace", mount_path=spec.workspace_mount_path)
            volume_mounts.append(workspace_mount)
            for init in spec.init_containers:
                init_containers.append(k8s_client.V1Container(
                    name=init.name,
                    image=init.image,
                    command=init.command,
                    env=[k8s_client.V1EnvVar(name=k, value=v) for k, v in init.env.items()] or None,
                    security_context=k8s_client.V1SecurityContext(
                        allow_privilege_escalation=False,
                        read_only_root_filesystem=False,  # git braucht Schreibzugriff im Workspace
                        run_as_non_root=True,
                        capabilities=k8s_client.V1Capabilities(drop=["ALL"]),
                    ),
                    volume_mounts=[workspace_mount, *secret_mounts],
                ))

        container = k8s_client.V1Container(
            name="scanner",
            image=spec.container_image,
            command=spec.command,
            env=env_vars or None,
            resources=k8s_client.V1ResourceRequirements(
                limits=spec.resource_limits,
                requests=spec.resource_limits,
            ),
            security_context=k8s_client.V1SecurityContext(
                allow_privilege_escalation=False,
                read_only_root_filesystem=True,
                run_as_non_root=True,
                capabilities=k8s_client.V1Capabilities(drop=["ALL"], add=spec.capabilities or None),
            ),
            volume_mounts=volume_mounts,
        )

        pod_spec = k8s_client.V1PodSpec(
            service_account_name=spec.service_account or DEFAULT_SERVICE_ACCOUNT,
            automount_service_account_token=False,
            restart_policy="Never",
            # Kurz halten: bei Timeout/Cancel soll SIGKILL zuegig kommen statt den
            # K8s-Default von 30s abzuwarten (Scanner reagieren nicht zuverlaessig auf SIGTERM).
            termination_grace_period_seconds=5,
            security_context=k8s_client.V1PodSecurityContext(
                run_as_non_root=True,
                run_as_user=65532,
                seccomp_profile=k8s_client.V1SeccompProfile(type="RuntimeDefault"),
            ),
            init_containers=init_containers or None,
            containers=[container],
            volumes=volumes,
        )

        labels = {
            "app.kubernetes.io/part-of": "ninko",
            "app.kubernetes.io/component": "security-scan",
            "ninko.io/scan-run-id": scan_run_id[:63],
            "ninko.io/scanner-id": spec.scanner_id[:63],
        }

        template = k8s_client.V1PodTemplateSpec(
            metadata=k8s_client.V1ObjectMeta(labels=labels), spec=pod_spec
        )

        job_spec = k8s_client.V1JobSpec(
            template=template,
            backoff_limit=0,
            # +15s Puffer ueber unserem eigenen Poll-Timeout: unser Timeout soll im
            # Normalfall zuerst greifen (klare ScanTimeoutError-Semantik). K8s'
            # activeDeadlineSeconds ist nur das Sicherheitsnetz, falls der Poll-Loop
            # selbst haengt/abstuerzt — dieser Fall wird unten explizit erkannt.
            active_deadline_seconds=int(spec.timeout_s) + 15,
            ttl_seconds_after_finished=300,
        )

        return k8s_client.V1Job(
            metadata=k8s_client.V1ObjectMeta(name=job_name, namespace=self.namespace, labels=labels),
            spec=job_spec,
        )

    def _build_network_policy(self, spec: ExecutionSpec, job_name: str) -> k8s_client.V1NetworkPolicy:
        """Egress-Policy pro Job. mode='none' -> nur DNS. Sonst: DNS + Allowlist,
        oder DNS + alles (mit WARNUNG geloggt), falls keine Allowlist vorliegt —
        die eigentliche Scope-Durchsetzung passiert in policy.py (Task #3);
        dies ist eine zusaetzliche Netzwerk-Verteidigungslinie, kein Ersatz dafuer.
        """
        dns_rule = k8s_client.V1NetworkPolicyEgressRule(
            to=None,
            ports=[
                k8s_client.V1NetworkPolicyPort(protocol="UDP", port=53),
                k8s_client.V1NetworkPolicyPort(protocol="TCP", port=53),
            ],
        )
        egress_rules = [dns_rule]

        if spec.network_policy.mode == "none":
            pass
        elif spec.network_policy.allowlist:
            peers = [
                k8s_client.V1NetworkPolicyPeer(ip_block=k8s_client.V1IPBlock(cidr=cidr))
                for cidr in spec.network_policy.allowlist
            ]
            egress_rules.append(k8s_client.V1NetworkPolicyEgressRule(to=peers))
        else:
            logger.warning(
                "Scanner %s: kein Egress-Allowlist gesetzt (mode=%s) — Egress bleibt "
                "ausserhalb der DNS-Regel unbeschraenkt auf Netzwerkebene. Scope-Durchsetzung "
                "muss ueber policy.py erfolgen.",
                spec.scanner_id,
                spec.network_policy.mode,
            )
            egress_rules.append(k8s_client.V1NetworkPolicyEgressRule(to=None))

        return k8s_client.V1NetworkPolicy(
            metadata=k8s_client.V1ObjectMeta(name=f"{job_name}-egress", namespace=self.namespace),
            spec=k8s_client.V1NetworkPolicySpec(
                pod_selector=k8s_client.V1LabelSelector(
                    match_labels={"job-name": job_name}
                ),
                policy_types=["Egress"],
                egress=egress_rules,
            ),
        )

    # ── Ausfuehrung ───────────────────────────────────────────────────

    async def run(self, spec: ExecutionSpec, *, scan_run_id: str) -> ScannerExecutionResult:
        """Erstellt Job+NetworkPolicy, wartet auf Terminierung, liefert Ergebnis,
        raeumt danach auf (immer, auch bei Fehler/Timeout)."""
        self._ensure_clients()
        job_name = _sanitize_job_name(spec.scanner_id, scan_run_id)
        started = time.monotonic()

        job_manifest = self._build_job_manifest(spec, job_name, scan_run_id)
        netpol_manifest = self._build_network_policy(spec, job_name)

        try:
            await asyncio.to_thread(
                self._networking_api.create_namespaced_network_policy, self.namespace, netpol_manifest
            )
            await asyncio.to_thread(self._batch_api.create_namespaced_job, self.namespace, job_manifest)
            logger.info("Security-Scan-Job erstellt: %s (scanner=%s)", job_name, spec.scanner_id)

            result = await self._wait_and_collect(job_name, spec, started)
            return result
        except ApiException as exc:
            raise ScanExecutionError(f"Kubernetes-API-Fehler beim Scan-Job {job_name}: {exc.reason}") from exc
        finally:
            await self._cleanup(job_name)

    async def _wait_and_collect(
        self, job_name: str, spec: ExecutionSpec, started: float
    ) -> ScannerExecutionResult:
        deadline = started + spec.timeout_s
        while True:
            job = await asyncio.to_thread(self._batch_api.read_namespaced_job_status, job_name, self.namespace)
            status = job.status
            if status.succeeded or status.failed:
                break
            if time.monotonic() > deadline:
                raise ScanTimeoutError(f"Scan-Job {job_name} hat Timeout ({spec.timeout_s}s) ueberschritten")
            await asyncio.sleep(_POLL_INTERVAL_S)

        # Sicherheitsnetz: Falls Kubernetes' activeDeadlineSeconds vor unserem
        # eigenen Poll-Timeout zugeschlagen hat (z.B. Poll-Loop kurzzeitig verzoegert),
        # muss das trotzdem als Timeout und NICHT als normaler "failed" Run erkannt
        # werden — sonst wuerden wir versuchen, Logs eines bereits terminierenden
        # Pods zu lesen und einen irrefuehrenden generischen Fehler melden.
        for condition in status.conditions or []:
            if condition.type == "Failed" and condition.reason == "DeadlineExceeded":
                raise ScanTimeoutError(
                    f"Scan-Job {job_name} wurde von Kubernetes wegen activeDeadlineSeconds abgebrochen"
                )

        pods = await asyncio.to_thread(
            self._core_api.list_namespaced_pod, self.namespace, label_selector=f"job-name={job_name}"
        )
        if not pods.items:
            raise ScanExecutionError(f"Kein Pod fuer Job {job_name} gefunden")
        pod = pods.items[0]
        pod_name = pod.metadata.name

        exit_code = 1
        for cs in pod.status.container_statuses or []:
            if cs.name == "scanner" and cs.state and cs.state.terminated:
                exit_code = cs.state.terminated.exit_code

        # _preload_content=False + manuelles Decode: der generierte Client versucht
        # sonst json.loads() auf die rohen Log-Bytes, scheitert (kein JSON) und faellt
        # auf str(bytes) statt bytes.decode() zurueck -> korrupter "b'...'"-String.
        raw_response = await asyncio.to_thread(
            self._core_api.read_namespaced_pod_log,
            pod_name,
            self.namespace,
            container="scanner",
            _preload_content=False,
        )
        raw_bytes = raw_response.data
        truncated = False
        if len(raw_bytes) > spec.max_output_bytes:
            raw_bytes = raw_bytes[: spec.max_output_bytes]
            truncated = True
        raw_logs = raw_bytes.decode("utf-8", errors="replace")

        return ScannerExecutionResult(
            scanner_id=spec.scanner_id,
            exit_code=exit_code,
            stdout=raw_logs,
            stderr="",
            truncated=truncated,
            duration_s=time.monotonic() - started,
            job_name=job_name,
        )

    async def _cleanup(self, job_name: str) -> None:
        try:
            await asyncio.to_thread(
                self._batch_api.delete_namespaced_job,
                job_name,
                self.namespace,
                propagation_policy="Background",
            )
        except ApiException as exc:
            if exc.status != 404:
                logger.warning("Cleanup Job %s fehlgeschlagen: %s", job_name, exc.reason)
        try:
            await asyncio.to_thread(
                self._networking_api.delete_namespaced_network_policy, f"{job_name}-egress", self.namespace
            )
        except ApiException as exc:
            if exc.status != 404:
                logger.warning("Cleanup NetworkPolicy %s fehlgeschlagen: %s", job_name, exc.reason)


_executor: K8sJobExecutor | None = None


def get_executor() -> K8sJobExecutor:
    global _executor
    if _executor is None:
        _executor = K8sJobExecutor()
    return _executor
