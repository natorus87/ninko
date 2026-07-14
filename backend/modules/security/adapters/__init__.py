"""Scanner-Adapter-Registrierung.

Jeder Adapter registriert sich hier explizit — kein Auto-Discovery ueber
Filesystem-Scans, damit niemals ein unbeabsichtigt im Verzeichnis liegender
Adapter automatisch aktiv wird (siehe Auftrag: "Kein Fallback auf freien
Modus" / "Unbekannte Scanner duerfen niemals automatisch ausgefuehrt werden").

Live gegen einen echten Cluster verifiziert: Trivy, Gitleaks (siehe
project_security_core.md). Die restlichen 6 sind strukturell konsistent und
unit-getestet, aber NICHT live gegen einen echten Scanner-Lauf verifiziert —
insbesondere Kubescape (komplexes, ungeprueftes JSON-Schema) und Garak
(Text-Summary-Parsing statt vollem JSONL-Report) haben dokumentierte
Unsicherheiten, siehe die jeweiligen Modul-Docstrings.
"""

from __future__ import annotations

from ..scanner_registry import get_scanner_registry
from .checkov import CHECKOV_DEFINITION, CheckovAdapter
from .garak import GARAK_DEFINITION, GarakAdapter
from .gitleaks import GITLEAKS_DEFINITION, GitleaksAdapter
from .kubelinter import KUBELINTER_DEFINITION, KubeLinterAdapter
from .kubescape import KUBESCAPE_DEFINITION, KubescapeAdapter
from .nmap import NMAP_DEFINITION, NmapAdapter
from .nuclei import NUCLEI_DEFINITION, NucleiAdapter
from .testssl import TESTSSL_DEFINITION, TestSSLAdapter
from .trivy import TRIVY_DEFINITION, TrivyAdapter

_ADAPTERS = (
    (TRIVY_DEFINITION, TrivyAdapter),
    (GITLEAKS_DEFINITION, GitleaksAdapter),
    (CHECKOV_DEFINITION, CheckovAdapter),
    (KUBESCAPE_DEFINITION, KubescapeAdapter),
    (KUBELINTER_DEFINITION, KubeLinterAdapter),
    (NMAP_DEFINITION, NmapAdapter),
    (NUCLEI_DEFINITION, NucleiAdapter),
    (TESTSSL_DEFINITION, TestSSLAdapter),
    (GARAK_DEFINITION, GarakAdapter),
)


def register_all_adapters() -> None:
    registry = get_scanner_registry()
    for definition, adapter_cls in _ADAPTERS:
        if not registry.is_registered(definition.id):
            registry.register(definition, adapter_cls())
