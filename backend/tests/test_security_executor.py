"""Unit-Tests fuer K8sJobExecutor (Task 2) — gemockter kubernetes-Client.

Fokus: sicherheitskritische Eigenschaften des Job-Manifests (non-root,
read-only-rootfs, dropped capabilities, kein Privilege-Escalation, kein
Token-Automount), Timeout-/DeadlineExceeded-Erkennung, korrektes Log-Decode.

Ein echter End-to-End-Test gegen einen laufenden Cluster wurde manuell
verifiziert (siehe .claude/memory/project_security_core.md) — hier nur
gemockt, damit CI ohne Cluster-Zugriff laeuft.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from modules.security.executor import (
    K8sJobExecutor,
    ScanExecutionError,
    ScanTimeoutError,
    _sanitize_job_name,
)
from modules.security.scanner_adapter import ExecutionSpec, InitContainerSpec, NetworkPolicy, VolumeMount

pytestmark = pytest.mark.unit


# ── Job-Name-Sanitizing ───────────────────────────────────────────────────


def test_sanitize_job_name_is_dns1123_compliant():
    name = _sanitize_job_name("trivy", "abcdef1234567890")
    assert len(name) <= 63
    assert name == name.lower()
    assert all(c.isalnum() or c == "-" for c in name)
    assert not name.startswith("-")
    assert not name.endswith("-")


def test_sanitize_job_name_unique_across_calls():
    n1 = _sanitize_job_name("trivy", "run-1")
    n2 = _sanitize_job_name("trivy", "run-1")
    assert n1 != n2  # zufaelliges Suffix verhindert Namenskollisionen


# ── Job-Manifest: Security-Context ───────────────────────────────────────


def _executor() -> K8sJobExecutor:
    ex = K8sJobExecutor()
    ex._batch_api = MagicMock()
    ex._core_api = MagicMock()
    ex._networking_api = MagicMock()
    return ex


def _spec(**overrides) -> ExecutionSpec:
    defaults = {
        "scanner_id": "trivy",
        "container_image": "aquasec/trivy:0.55.0",
        "command": ["trivy", "image", "--format", "json", "foo:latest"],
        "timeout_s": 120,
    }
    defaults.update(overrides)
    return ExecutionSpec(**defaults)


def test_job_manifest_container_security_context_is_locked_down():
    executor = _executor()
    job = executor._build_job_manifest(_spec(), "scan-trivy-abc123-xyz", "run-1")
    container = job.spec.template.spec.containers[0]
    sc = container.security_context
    assert sc.allow_privilege_escalation is False
    assert sc.read_only_root_filesystem is True
    assert sc.run_as_non_root is True
    assert sc.capabilities.drop == ["ALL"]


def test_job_manifest_pod_disables_token_automount_and_short_grace_period():
    executor = _executor()
    job = executor._build_job_manifest(_spec(), "scan-trivy-abc123-xyz", "run-1")
    pod_spec = job.spec.template.spec
    assert pod_spec.automount_service_account_token is False
    assert pod_spec.restart_policy == "Never"
    assert pod_spec.termination_grace_period_seconds == 5
    assert pod_spec.security_context.run_as_non_root is True


def test_job_manifest_command_passed_as_is_no_shell_wrapper():
    executor = _executor()
    spec = _spec(command=["trivy", "image", "foo:latest"])
    job = executor._build_job_manifest(spec, "scan-trivy-abc123-xyz", "run-1")
    container = job.spec.template.spec.containers[0]
    assert container.command == ["trivy", "image", "foo:latest"]
    assert "sh" not in container.command
    assert "-c" not in container.command


def test_job_manifest_active_deadline_has_buffer_over_client_timeout():
    executor = _executor()
    spec = _spec(timeout_s=60)
    job = executor._build_job_manifest(spec, "scan-trivy-abc123-xyz", "run-1")
    assert job.spec.active_deadline_seconds > 60
    assert job.spec.backoff_limit == 0


def test_job_manifest_capabilities_added_only_when_specified():
    executor = _executor()
    spec = _spec(capabilities=["NET_RAW"])
    job = executor._build_job_manifest(spec, "scan-nmap-abc123-xyz", "run-1")
    container = job.spec.template.spec.containers[0]
    assert container.security_context.capabilities.add == ["NET_RAW"]


def test_job_manifest_rejects_shell_string_lookalike_command():
    executor = _executor()
    spec = _spec(command=["trivy image; rm -rf /"])
    with pytest.raises(ValueError):
        executor._build_job_manifest(spec, "job-name", "run-1")


def test_job_manifest_labels_include_scan_run_and_scanner_id():
    executor = _executor()
    job = executor._build_job_manifest(_spec(), "scan-trivy-abc123-xyz", "run-42")
    labels = job.spec.template.metadata.labels
    assert labels["ninko.io/scan-run-id"] == "run-42"
    assert labels["ninko.io/scanner-id"] == "trivy"


def test_job_manifest_volume_mounts_default_read_only():
    executor = _executor()
    spec = _spec(volumes=[VolumeMount(name="cache", mount_path="/cache")])
    job = executor._build_job_manifest(spec, "job-name", "run-1")
    mounts = job.spec.template.spec.containers[0].volume_mounts
    cache_mount = next(m for m in mounts if m.mount_path == "/cache")
    assert cache_mount.read_only is True


# ── NetworkPolicy ─────────────────────────────────────────────────────────


def test_network_policy_mode_none_only_allows_dns():
    executor = _executor()
    spec = _spec(network_policy=NetworkPolicy(mode="none"))
    netpol = executor._build_network_policy(spec, "job-name")
    assert len(netpol.spec.egress) == 1
    ports = {p.port for p in netpol.spec.egress[0].ports}
    assert ports == {53}


def test_network_policy_with_allowlist_adds_ip_block_rule():
    executor = _executor()
    spec = _spec(
        network_policy=NetworkPolicy(mode="egress_allowlist", allowlist=["10.0.0.0/24"])
    )
    netpol = executor._build_network_policy(spec, "job-name")
    assert len(netpol.spec.egress) == 2
    assert netpol.spec.egress[1].to[0].ip_block.cidr == "10.0.0.0/24"


def test_network_policy_target_only_without_allowlist_denies_non_dns_egress():
    """Regressionstest: eine leere Allowlist unter mode='target_only'/'egress_allowlist'
    darf NIEMALS stillschweigend zu offenem Egress fuehren (frueherer Bug) — nur DNS
    ist erlaubt, exakt wie mode='none'. Offener Zugriff muss explizit ueber
    mode='open' angefordert werden (siehe naechster Test)."""
    executor = _executor()
    spec = _spec(network_policy=NetworkPolicy(mode="target_only", allowlist=[]))
    netpol = executor._build_network_policy(spec, "job-name")
    assert len(netpol.spec.egress) == 1
    ports = {p.port for p in netpol.spec.egress[0].ports}
    assert ports == {53}


def test_network_policy_mode_open_falls_back_to_open_egress_with_warning(caplog):
    executor = _executor()
    spec = _spec(network_policy=NetworkPolicy(mode="open", allowlist=[]))
    with caplog.at_level("WARNING"):
        netpol = executor._build_network_policy(spec, "job-name")
    assert len(netpol.spec.egress) == 2
    assert netpol.spec.egress[1].to is None
    assert any("mode='open'" in r.message for r in caplog.records)


def test_network_policy_pod_selector_matches_job_name():
    executor = _executor()
    netpol = executor._build_network_policy(_spec(), "scan-trivy-abc")
    assert netpol.spec.pod_selector.match_labels == {"job-name": "scan-trivy-abc"}


# ── Wait/Timeout-Erkennung (gemockt) ───────────────────────────────────────


def _fake_job_status(*, succeeded=0, failed=0, conditions=None):
    return SimpleNamespace(
        status=SimpleNamespace(succeeded=succeeded, failed=failed, conditions=conditions or [])
    )


def _fake_pod_list(exit_code=0):
    container_status = SimpleNamespace(
        name="scanner", state=SimpleNamespace(terminated=SimpleNamespace(exit_code=exit_code))
    )
    pod = SimpleNamespace(
        metadata=SimpleNamespace(name="scan-pod-abc"),
        status=SimpleNamespace(container_statuses=[container_status]),
    )
    return SimpleNamespace(items=[pod])


@pytest.mark.asyncio
async def test_wait_and_collect_deadline_exceeded_condition_raises_timeout():
    executor = _executor()
    executor._batch_api.read_namespaced_job_status.return_value = _fake_job_status(
        failed=1,
        conditions=[SimpleNamespace(type="Failed", reason="DeadlineExceeded")],
    )
    import time

    with pytest.raises(ScanTimeoutError):
        await executor._wait_and_collect("job-name", _spec(timeout_s=5), time.monotonic())


@pytest.mark.asyncio
async def test_wait_and_collect_reads_decoded_logs_on_success():
    executor = _executor()
    executor._batch_api.read_namespaced_job_status.return_value = _fake_job_status(succeeded=1)
    executor._core_api.list_namespaced_pod.return_value = _fake_pod_list(exit_code=0)
    fake_response = SimpleNamespace(data=b"finding: CVE-2024-1\n")
    executor._core_api.read_namespaced_pod_log.return_value = fake_response

    import time

    result = await executor._wait_and_collect("job-name", _spec(), time.monotonic())
    assert result.exit_code == 0
    assert result.stdout == "finding: CVE-2024-1\n"
    assert not result.stdout.startswith("b'")


@pytest.mark.asyncio
async def test_wait_and_collect_truncates_oversized_output():
    executor = _executor()
    executor._batch_api.read_namespaced_job_status.return_value = _fake_job_status(succeeded=1)
    executor._core_api.list_namespaced_pod.return_value = _fake_pod_list(exit_code=0)
    executor._core_api.read_namespaced_pod_log.return_value = SimpleNamespace(data=b"x" * 100)

    import time

    spec = _spec()
    spec = spec.model_copy(update={"max_output_bytes": 10})
    result = await executor._wait_and_collect("job-name", spec, time.monotonic())
    assert result.truncated is True
    assert len(result.stdout) == 10


@pytest.mark.asyncio
async def test_wait_and_collect_no_pod_found_raises_execution_error():
    executor = _executor()
    executor._batch_api.read_namespaced_job_status.return_value = _fake_job_status(succeeded=1)
    executor._core_api.list_namespaced_pod.return_value = SimpleNamespace(items=[])

    import time

    with pytest.raises(ScanExecutionError):
        await executor._wait_and_collect("job-name", _spec(), time.monotonic())


# ── Init-Container / Secret-Mounting (Task 7) ─────────────────────────────


def test_job_manifest_without_init_containers_has_no_workspace_volume():
    executor = _executor()
    job = executor._build_job_manifest(_spec(), "job-name", "run-1")
    pod_spec = job.spec.template.spec
    assert pod_spec.init_containers is None
    volume_names = {v.name for v in pod_spec.volumes}
    assert "workspace" not in volume_names


def test_job_manifest_with_init_container_shares_workspace_volume():
    executor = _executor()
    init = InitContainerSpec(
        name="git-clone", image="alpine/git:2.45.2",
        command=["git", "clone", "--depth", "1", "https://example.com/repo.git", "/workspace"],
    )
    spec = _spec(init_containers=[init])
    job = executor._build_job_manifest(spec, "job-name", "run-1")
    pod_spec = job.spec.template.spec

    assert len(pod_spec.init_containers) == 1
    assert pod_spec.init_containers[0].name == "git-clone"
    assert pod_spec.init_containers[0].command == init.command

    volume_names = {v.name for v in pod_spec.volumes}
    assert "workspace" in volume_names

    main_mount_paths = {m.mount_path for m in pod_spec.containers[0].volume_mounts}
    init_mount_paths = {m.mount_path for m in pod_spec.init_containers[0].volume_mounts}
    assert "/workspace" in main_mount_paths
    assert "/workspace" in init_mount_paths


def test_job_manifest_init_container_hardened_security_context():
    executor = _executor()
    init = InitContainerSpec(name="git-clone", image="alpine/git:2.45.2", command=["git", "clone", "x", "/workspace"])
    spec = _spec(init_containers=[init])
    job = executor._build_job_manifest(spec, "job-name", "run-1")
    init_sc = job.spec.template.spec.init_containers[0].security_context
    assert init_sc.allow_privilege_escalation is False
    assert init_sc.run_as_non_root is True
    assert init_sc.capabilities.drop == ["ALL"]


def test_job_manifest_rejects_init_container_shell_string():
    executor = _executor()
    init = InitContainerSpec(name="bad", image="x", command=["git clone x; rm -rf /"])
    spec = _spec(init_containers=[init])
    with pytest.raises(ValueError):
        executor._build_job_manifest(spec, "job-name", "run-1")


def test_job_manifest_secret_refs_mounted_read_only():
    executor = _executor()
    spec = _spec(secret_refs=["kubeconfig-prod-cluster"])
    job = executor._build_job_manifest(spec, "job-name", "run-1")
    container = job.spec.template.spec.containers[0]
    secret_mount = next(m for m in container.volume_mounts if m.mount_path == "/secrets/kubeconfig-prod-cluster")
    assert secret_mount.read_only is True

    secret_volume = next(v for v in job.spec.template.spec.volumes if v.name == "secret-kubeconfig-prod-cluster")
    assert secret_volume.secret.secret_name == "kubeconfig-prod-cluster"


def test_job_manifest_secret_refs_also_mounted_in_init_containers():
    executor = _executor()
    init = InitContainerSpec(
        name="git-clone", image="alpine/git:2.45.2",
        command=["git", "clone", "https://example.com/repo.git", "/workspace"],
        env={"GIT_ASKPASS": "/secrets/git-token/askpass.sh"},
    )
    spec = _spec(secret_refs=["git-token"], init_containers=[init])
    job = executor._build_job_manifest(spec, "job-name", "run-1")
    init_mount_paths = {m.mount_path for m in job.spec.template.spec.init_containers[0].volume_mounts}
    assert "/secrets/git-token" in init_mount_paths
