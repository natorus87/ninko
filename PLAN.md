
Spezifikation: Deterministische Vor-Strukturierung vor dem Planner

Ziel

Vor jedem eigentlichen Planner-LLM-Call soll aus der User-Anfrage deterministisch eine strukturierte Task-Skizze erzeugt werden.

Diese Task-Skizze reduziert Interpretationsspielraum für den Planner und soll:
	•	Halluzinationen verringern
	•	Drift reduzieren
	•	Routing stabilisieren
	•	Kontextverlust vermeiden
	•	Mehrdeutige Aufgaben in eine feste Struktur bringen
	•	die spätere Planner-Ausgabe leichter validierbar machen

Der Planner soll nicht mehr die Aufgabe frei interpretieren, sondern nur noch auf Basis der Task-Skizze:
	•	Module auswählen
	•	Schritte planen
	•	die Reihenfolge bestimmen
	•	Sicherheits- und Ausführungsgrenzen beachten

⸻

1. Architekturziel

Neue Pipeline

Bisher grob:

User Input -> CoreAgent / Routing / Planner

Neu:

User Input -> Deterministic Pre-Structurer -> TaskSketch -> Planner -> Plan -> Executor/Synthesizer

Verantwortlichkeiten

Deterministic Pre-Structurer

Verantwortlich für:
	•	Extraktion des eigentlichen Ziels
	•	Erkennung von Intent
	•	Erkennung von Risiko
	•	Erkennung von benötigter Tool-Nutzung
	•	Erkennung von Komplexität
	•	Extraktion von Entitäten
	•	Ermittlung von Kandidaten-Modulen
	•	Extraktion von Constraints
	•	Vor-Klassifikation der Antwortform

Planner

Verantwortlich nur für:
	•	Modulauswahl aus Kandidaten
	•	Step-Reihenfolge
	•	Delegation an interne Worker
	•	Replan bei Fehlschlag
	•	strukturierte Plan-JSON-Ausgabe

⸻

2. Nicht-Ziele

Diese Vor-Strukturierung soll nicht:
	•	freie natürliche Sprache generieren
	•	direkt Tools ausführen
	•	Sicherheitsentscheidungen final treffen
	•	finale Antworten formulieren
	•	beliebige Semantik „erraten“
	•	Langzeitgedächtnis auswerten
	•	einen vollständigen Agent ersetzen

⸻

3. Kernprinzipien
	1.	Deterministisch vor probabilistisch
Alles, was mit Regeln, Mapping, Parsing, Klassifikation und Heuristik geht, soll ohne LLM passieren.
	2.	Kleine feste Ontologie statt freie Interpretation
Die Vor-Strukturierung arbeitet mit festen Kategorien und enums.
	3.	Immer strukturierter Output
Keine freie Textantwort, sondern ein validierbares JSON-Objekt.
	4.	Explizite Unsicherheit statt stilles Raten
Wenn unklar, dann unknown, ambiguous, requires_planner_resolution.
	5.	Lieber grob korrekt als scheinbar intelligent
Vor-Strukturierung soll robust und wiederholbar sein, nicht kreativ.

⸻

4. Datenmodell: TaskSketch

JSON-Schema fachlich

{
  "version": "1.0",
  "source": {
    "user_message": "string",
    "conversation_turn_id": "string",
    "session_id": "string"
  },
  "task": {
    "intent": "answer|investigate|act|plan|workflow|compare|summarize|unknown",
    "primary_goal": "string",
    "secondary_goals": ["string"],
    "requested_output": [
      "answer",
      "diagnosis",
      "next_step",
      "plan",
      "execution",
      "comparison",
      "summary",
      "report"
    ],
    "complexity": "simple|multi_step|compound|unknown",
    "needs_tools": true,
    "needs_fresh_state": true,
    "needs_evidence": true,
    "user_explicit_action_request": false
  },
  "risk": {
    "level": "low|medium|high|critical",
    "destructive_potential": false,
    "write_intent_detected": false,
    "external_side_effects_possible": false,
    "approval_required": false,
    "reason_codes": ["READ_ONLY_DIAGNOSTIC"]
  },
  "scope": {
    "domain": "infra|kubernetes|gitlab|monitoring|network|database|files|general|unknown",
    "candidate_modules": ["kubernetes", "gitlab", "postgresql"],
    "candidate_modules_ranked": [
      { "module": "gitlab", "score": 0.92, "reasons": ["keyword:gitlab", "entity:deployment"] }
    ],
    "multi_module": true,
    "entities": {
      "systems": ["gitlab"],
      "services": ["postgresql", "traefik"],
      "hosts": [],
      "namespaces": [],
      "clusters": [],
      "resources": [],
      "time_refs": ["seit dem letzten deployment"]
    }
  },
  "constraints": {
    "execution_mode": "read_only|guarded_write|planner_decides",
    "time_sensitivity": "normal|urgent|unknown",
    "response_style": "concise|normal|detailed|unknown",
    "must_not_do": ["destructive_changes_without_approval"],
    "must_include": ["evidence", "safe_next_step"],
    "user_constraints": []
  },
  "routing_hints": {
    "preferred_worker_type": "direct_answer|explorer|operator|planner|workflow",
    "should_delegate": true,
    "should_avoid_direct_answer": true,
    "should_collect_state_before_answer": true
  },
  "uncertainty": {
    "ambiguous": false,
    "missing_information": [],
    "open_questions": [],
    "confidence": 0.86
  },
  "debug": {
    "matched_rules": [
      "INTENT_INVESTIGATE_DIAGNOSIS",
      "RISK_READ_ONLY",
      "MODULE_GITLAB",
      "MODULE_POSTGRESQL",
      "MODULE_TRAEFIK"
    ],
    "tokens": {
      "normalized_input": ["gitlab", "letztes", "deployment", "postgresql", "ingress", "naechster", "sicherer", "schritt"]
    }
  }
}


⸻

5. Feste Enums

Intent

Erlaubte Werte:
	•	answer
reine Wissens- oder Erklärfrage
	•	investigate
Zustand prüfen, Ursache finden, analysieren, diagnostizieren
	•	act
Nutzer will explizit eine Handlung oder Änderung
	•	plan
Nutzer will einen Plan, ein Vorgehen, eine Strategie
	•	workflow
mehrstufige, explizit orchestrierte Aufgabe
	•	compare
Nutzer will Optionen vergleichen
	•	summarize
Nutzer will etwas zusammenfassen
	•	unknown

Complexity
	•	simple
	•	multi_step
	•	compound
	•	unknown

Risk Level
	•	low
	•	medium
	•	high
	•	critical

Execution Mode
	•	read_only
	•	guarded_write
	•	planner_decides

Preferred Worker
	•	direct_answer
	•	explorer
	•	operator
	•	planner
	•	workflow

⸻

6. Eingaben

Minimaler Input

Der Pre-Structurer bekommt:
	•	aktuelle User-Nachricht
	•	optional die letzten 1–2 User- und Assistant-Turns
	•	bekannte Modul-Metadaten
	•	optionale Session-Metadaten

Modul-Metadaten

Jedes Modul soll eine kleine, deterministisch nutzbare Beschreibung liefern:

{
  "name": "gitlab",
  "keywords": ["gitlab", "pipeline", "merge request", "runner", "deployment", "repo", "ci", "cd"],
  "entities": ["project", "pipeline", "job", "runner"],
  "domain": "gitlab",
  "read_only_capabilities": ["inspect pipelines", "inspect jobs", "read project state"],
  "write_capabilities": ["rerun pipeline", "trigger deployment"]
}

Die Modul-Metadaten sollen nicht vom LLM interpretiert werden, sondern direkt zur Heuristik dienen.

⸻

7. Verarbeitungsschritte

Schritt 1: Normalisierung

Anforderungen
	•	lowercasing
	•	Unicode-Normalisierung
	•	Sonderzeichen bereinigen
	•	deutsche Umlaute konsistent behandeln
	•	Tokenisierung
	•	Stoppwörter optional für Nebenanalysen
	•	Originaltext immer erhalten

Beispiel

Input:
"Prüf bitte ob PostgreSQL oder der Ingress schuld ist!"

Normalisiert:
["pruef", "bitte", "ob", "postgresql", "oder", "der", "ingress", "schuld", "ist"]

⸻

Schritt 2: Intent-Erkennung

Intent-Erkennung erfolgt deterministisch über:
	•	Verben
	•	Phrasen
	•	Fragestruktur
	•	Handlungsmarker
	•	Diagnosemarker
	•	Planungsmarker

Beispielhafte Regeln

investigate

wenn Begriffe vorkommen wie:
	•	prüfen
	•	check
	•	analysiere
	•	untersuche
	•	finde heraus
	•	woran liegt
	•	schuld
	•	diagnose
	•	warum funktioniert nicht
	•	root cause
	•	problem
	•	issue
	•	fehler
	•	status prüfen

act

wenn Begriffe vorkommen wie:
	•	starte
	•	stoppe
	•	ändere
	•	deploye
	•	lösche
	•	führe aus
	•	setze
	•	update
	•	trigger
	•	erstelle
	•	restart

plan

wenn Begriffe vorkommen wie:
	•	plan
	•	wie soll ich
	•	schritt für schritt
	•	vorgehen
	•	strategie
	•	konzept
	•	roadmap

compare

wenn Begriffe vorkommen wie:
	•	vergleich
	•	unterschied
	•	besser
	•	versus
	•	vs
	•	pros und cons

answer

wenn erkennbar rein erklärend:
	•	was ist
	•	wie funktioniert
	•	erkläre
	•	beschreibe

Konfliktregel

Wenn mehrere Intents matchen:

Priorität:
act > investigate > workflow > plan > compare > summarize > answer > unknown

Zusätzliche Korrektur:
Wenn Handlungsverb nur hypothetisch ist, aber Diagnose im Vordergrund steht, dann investigate.

Beispiel:
„prüf bitte und sag mir den nächsten Schritt“
=> investigate, nicht act

⸻

Schritt 3: Ziel-Extraktion

Extrahiere:
	•	primary_goal
	•	secondary_goals
	•	requested_output

Regeln

Primary Goal

Knappe, normalisierte Zusammenfassung des Hauptziels in deterministischer Form.

Beispiel:
User:
„Mein GitLab spinnt seit dem letzten Deployment, prüf bitte ob PostgreSQL oder der Ingress schuld ist und sag mir den nächsten sicheren Schritt.“

Primary goal:
"Diagnose der Ursache eines GitLab-Problems nach Deployment"

Secondary Goals
	•	"Prüfung PostgreSQL"
	•	"Prüfung Ingress"
	•	"Empfehlung nächster sicherer Schritt"

Requested Output Mapping

Erkannt über Formulierungen:
	•	„sag mir warum“ -> diagnosis
	•	„nächster Schritt“ -> next_step
	•	„mach es“ -> execution
	•	„erkläre“ -> answer
	•	„fass zusammen“ -> summary

⸻

Schritt 4: Komplexitätserkennung

Regeln

simple
	•	ein klarer Intent
	•	ein System
	•	keine Nebenbedingung
	•	keine Mehrfachziele
	•	keine zeitliche oder konditionale Verknüpfung

multi_step
	•	ein Hauptziel, aber mehrere Prüfschritte nötig
	•	oder Diagnose plus Empfehlung
	•	oder State holen + auswerten

compound
	•	mehrere Teilziele
	•	mehrere Systeme
	•	mehrere konkurrierende Ursachen
	•	Kombination aus Diagnose und Handlung
	•	Workflow-/Orchestrierungscharakter

Heuristiken

Komplexitätsindikatoren:
	•	„und“
	•	„oder“
	•	„danach“
	•	„falls“
	•	„wenn“
	•	mehrere Systeme
	•	mehrere Entitäten
	•	sowohl Diagnose als auch Handlung
	•	sowohl Vergleich als auch Entscheidung

⸻

Schritt 5: Tool-Bedarf und Fresh-State-Bedarf

needs_tools = true, wenn:
	•	Diagnose eines Live-Systems
	•	Zustandsprüfung
	•	Logs / Pipelines / Cluster / Monitoring / Datenbank
	•	aktuelle Informationen nötig
	•	User explizit „prüf“, „check“, „sieh nach“

needs_fresh_state = true, wenn:
	•	Userproblem zeitbezogen ist
	•	Live-Zustand relevant ist
	•	Begriffe wie „gerade“, „seit gestern“, „nach Deployment“, „jetzt“, „aktuell“ vorkommen

needs_evidence = true, wenn:
	•	investigate
	•	compare
	•	act bei riskanten Themen
	•	Ursachenanalyse
	•	Empfehlung eines nächsten Schrittes

⸻

Schritt 6: Risikoermittlung

Risikostufe wird vorläufig bestimmt.

low

read-only, Diagnose, Erklärung, Statusprüfung

medium

potentielle Konfigänderung, Restart, kontrollierte Operation

high

Deployment, Änderung produktiver Konfiguration, Zugriff auf externe Systeme

critical

Löschen, Reset, irreversible Änderungen, weitreichende Prod-Auswirkungen

Risk-Reason-Codes

Mögliche Codes:
	•	READ_ONLY_DIAGNOSTIC
	•	WRITE_VERB_DETECTED
	•	DELETE_VERB_DETECTED
	•	PRODUCTION_IMPACT_POSSIBLE
	•	EXTERNAL_SIDE_EFFECTS
	•	AMBIGUOUS_ACTION_REQUEST
	•	SENSITIVE_SYSTEM_TARGET

approval_required = true, wenn:
	•	risk >= medium und write intent vorhanden
	•	oder destructive potential true
	•	oder external side effects true

⸻

Schritt 7: Entitäten extrahieren

Extrahiere möglichst deterministisch:
	•	Systeme
	•	Services
	•	Module
	•	Ressourcen
	•	Hosts
	•	Namespaces
	•	Cluster
	•	Zeitreferenzen

Quellen
	•	Regex / Lexika / bekannte Modul-Keywords
	•	technische Namen direkt aus Usertext
	•	einfache NER-ähnliche Heuristik

Beispiele

Text:
"Check im Namespace payments die letzten Pods im Cluster prod-eu"

Extrahieren:

{
  "systems": ["kubernetes"],
  "services": [],
  "hosts": [],
  "namespaces": ["payments"],
  "clusters": ["prod-eu"],
  "resources": ["pods"],
  "time_refs": ["die letzten"]
}


⸻

Schritt 8: Kandidaten-Module bestimmen

Module werden nicht frei geraten, sondern durch Scores ermittelt.

Score-Komponenten

Jedes Modul bekommt Punkte aus:
	•	Keyword Match
	•	Entity Match
	•	Domain Match
	•	Verb-Kontext
	•	historischer Präzedenzfall optional
	•	Negativmatch optional

Beispielgewichtung
	•	exakter Modulname im Text: +0.50
	•	relevantes Keyword: +0.20
	•	relevante Entity: +0.15
	•	passender Domain-Kontext: +0.10
	•	Konflikt mit anderem Modul: -0.10
	•	nur schwaches Alias: +0.05

Ausgabe
	•	nur Top-N, z. B. 5
	•	sortiert nach Score
	•	jede Auswahl mit Gründen

⸻

8. Routing-Hints

Der Pre-Structurer soll eine Empfehlung geben, kein finales Routing.

Regeln

preferred_worker_type = direct_answer

wenn:
	•	intent = answer
	•	complexity = simple
	•	needs_tools = false
	•	risk = low

preferred_worker_type = explorer

wenn:
	•	intent = investigate
	•	execution_mode = read_only
	•	needs_tools = true

preferred_worker_type = operator

wenn:
	•	intent = act
	•	write intent erkannt
	•	approval required wahrscheinlich

preferred_worker_type = planner

wenn:
	•	multi_step oder compound
	•	mehrere Kandidatenmodule
	•	Unsicherheit vorhanden

preferred_worker_type = workflow

wenn:
	•	ausdrücklicher Workflowcharakter
	•	Mehrphasenaufgabe
	•	konditionale Kette

⸻

9. Unsicherheitsmodell

Der Pre-Structurer soll Unsicherheit explizit markieren.

ambiguous = true, wenn:
	•	mehrere Intents ähnlich stark
	•	mehrere inkompatible Kandidatenmodule
	•	unklare Aktion
	•	Ziel unklar
	•	notwendige Entitäten fehlen

missing_information

Beispiele:
	•	target_environment_missing
	•	namespace_missing
	•	time_scope_missing

open_questions

Nur technische offene Punkte, keine freie Rückfrage.

⸻

10. Harte Regeln

Regel A

Der Pre-Structurer darf niemals Tools ausführen.

Regel B

Der Pre-Structurer darf niemals freie Handlungsempfehlungen formulieren.

Regel C

Der Pre-Structurer darf niemals finale Sicherheitsfreigaben erteilen.

Regel D

Wenn unklar, dann:
	•	unknown
	•	ambiguous = true
	•	should_delegate = true

Regel E

Wenn needs_tools = true, dann:
	•	should_avoid_direct_answer = true

⸻

11. Implementierungsdesign

Neue Komponente

Vorgeschlagener Name:
	•	DeterministicTaskSketchBuilder
	•	alternativ PreStructurer

Dateien

Vorschlag:
	•	core/prestructure/task_sketch_builder.py
	•	core/prestructure/rules.py
	•	core/prestructure/module_matcher.py
	•	core/prestructure/schemas.py
	•	core/prestructure/normalizer.py
	•	tests/test_task_sketch_builder.py

⸻

12. Python-Datenmodelle

Pydantic-Modelle

from typing import List, Literal, Optional, Dict
from pydantic import BaseModel, Field

Intent = Literal["answer", "investigate", "act", "plan", "workflow", "compare", "summarize", "unknown"]
Complexity = Literal["simple", "multi_step", "compound", "unknown"]
RiskLevel = Literal["low", "medium", "high", "critical"]
ExecutionMode = Literal["read_only", "guarded_write", "planner_decides"]
WorkerType = Literal["direct_answer", "explorer", "operator", "planner", "workflow"]

class SourceInfo(BaseModel):
    user_message: str
    conversation_turn_id: Optional[str] = None
    session_id: Optional[str] = None

class RankedModule(BaseModel):
    module: str
    score: float
    reasons: List[str] = Field(default_factory=list)

class TaskInfo(BaseModel):
    intent: Intent
    primary_goal: str
    secondary_goals: List[str] = Field(default_factory=list)
    requested_output: List[str] = Field(default_factory=list)
    complexity: Complexity
    needs_tools: bool
    needs_fresh_state: bool
    needs_evidence: bool
    user_explicit_action_request: bool

class RiskInfo(BaseModel):
    level: RiskLevel
    destructive_potential: bool
    write_intent_detected: bool
    external_side_effects_possible: bool
    approval_required: bool
    reason_codes: List[str] = Field(default_factory=list)

class ScopeEntities(BaseModel):
    systems: List[str] = Field(default_factory=list)
    services: List[str] = Field(default_factory=list)
    hosts: List[str] = Field(default_factory=list)
    namespaces: List[str] = Field(default_factory=list)
    clusters: List[str] = Field(default_factory=list)
    resources: List[str] = Field(default_factory=list)
    time_refs: List[str] = Field(default_factory=list)

class ScopeInfo(BaseModel):
    domain: str
    candidate_modules: List[str] = Field(default_factory=list)
    candidate_modules_ranked: List[RankedModule] = Field(default_factory=list)
    multi_module: bool
    entities: ScopeEntities

class ConstraintInfo(BaseModel):
    execution_mode: ExecutionMode
    time_sensitivity: Literal["normal", "urgent", "unknown"] = "normal"
    response_style: Literal["concise", "normal", "detailed", "unknown"] = "normal"
    must_not_do: List[str] = Field(default_factory=list)
    must_include: List[str] = Field(default_factory=list)
    user_constraints: List[str] = Field(default_factory=list)

class RoutingHints(BaseModel):
    preferred_worker_type: WorkerType
    should_delegate: bool
    should_avoid_direct_answer: bool
    should_collect_state_before_answer: bool

class UncertaintyInfo(BaseModel):
    ambiguous: bool
    missing_information: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    confidence: float = 0.0

class DebugInfo(BaseModel):
    matched_rules: List[str] = Field(default_factory=list)
    tokens: Dict[str, List[str]] = Field(default_factory=dict)

class TaskSketch(BaseModel):
    version: str = "1.0"
    source: SourceInfo
    task: TaskInfo
    risk: RiskInfo
    scope: ScopeInfo
    constraints: ConstraintInfo
    routing_hints: RoutingHints
    uncertainty: UncertaintyInfo
    debug: DebugInfo


⸻

13. Builder-API

Öffentliche API

class DeterministicTaskSketchBuilder:
    def __init__(self, module_registry, config=None):
        ...

    def build(
        self,
        user_message: str,
        session_id: str | None = None,
        conversation_turn_id: str | None = None,
        recent_turns: list[dict] | None = None
    ) -> TaskSketch:
        ...

Builder-Ablauf

def build(...):
    normalized = normalize(user_message)
    intent = detect_intent(normalized, recent_turns)
    goals = extract_goals(user_message, intent)
    complexity = detect_complexity(normalized, goals)
    entities = extract_entities(normalized, module_registry)
    module_candidates = rank_modules(normalized, entities, module_registry)
    task_flags = infer_task_flags(intent, normalized, entities)
    risk = infer_risk(intent, normalized, entities, task_flags)
    constraints = infer_constraints(intent, normalized, risk)
    routing = infer_routing_hints(intent, complexity, task_flags, risk, module_candidates)
    uncertainty = infer_uncertainty(intent, module_candidates, entities, goals)
    debug = collect_debug(...)
    return TaskSketch(...)


⸻

14. Beispiel-Regeln in Pseudocode

Intent detection

def detect_intent(tokens: list[str], recent_turns=None) -> str:
    scores = {
        "answer": 0,
        "investigate": 0,
        "act": 0,
        "plan": 0,
        "workflow": 0,
        "compare": 0,
        "summarize": 0
    }

    if any(t in tokens for t in ["pruef", "check", "analysiere", "untersuche", "schuld", "warum", "fehler"]):
        scores["investigate"] += 3

    if any(t in tokens for t in ["starte", "stoppe", "aendere", "deploye", "loesche", "trigger"]):
        scores["act"] += 4

    if any(t in tokens for t in ["plan", "vorgehen", "strategie", "roadmap"]):
        scores["plan"] += 3

    if any(t in tokens for t in ["vergleich", "vs", "versus", "besser"]):
        scores["compare"] += 3

    if any(t in tokens for t in ["zusammenfassen", "fass", "summary"]):
        scores["summarize"] += 3

    if any(t in tokens for t in ["was", "wie", "erklaere"]) and max(scores.values()) == 0:
        scores["answer"] += 2

    best_intent = max(scores, key=scores.get)
    if scores[best_intent] == 0:
        return "unknown"
    return best_intent


⸻

Complexity detection

def detect_complexity(tokens, goals) -> str:
    connectors = sum(1 for t in tokens if t in ["und", "oder", "falls", "wenn", "danach"])
    goal_count = 1 + len(goals.secondary_goals)

    if goal_count <= 1 and connectors == 0:
        return "simple"

    if goal_count >= 3 or connectors >= 2:
        return "compound"

    return "multi_step"


⸻

Risk detection

def infer_risk(intent, tokens, entities, task_flags):
    write_verbs = {"starte", "stoppe", "aendere", "deploye", "trigger", "setze", "erstelle"}
    delete_verbs = {"loesche", "drop", "reset", "remove"}

    write_intent = any(t in write_verbs for t in tokens)
    delete_intent = any(t in delete_verbs for t in tokens)

    if delete_intent:
        return {
            "level": "critical",
            "destructive_potential": True,
            "write_intent_detected": True,
            "external_side_effects_possible": True,
            "approval_required": True,
            "reason_codes": ["DELETE_VERB_DETECTED"]
        }

    if write_intent:
        return {
            "level": "high",
            "destructive_potential": False,
            "write_intent_detected": True,
            "external_side_effects_possible": True,
            "approval_required": True,
            "reason_codes": ["WRITE_VERB_DETECTED"]
        }

    if intent == "investigate":
        return {
            "level": "low",
            "destructive_potential": False,
            "write_intent_detected": False,
            "external_side_effects_possible": False,
            "approval_required": False,
            "reason_codes": ["READ_ONLY_DIAGNOSTIC"]
        }

    return {
        "level": "medium",
        "destructive_potential": False,
        "write_intent_detected": False,
        "external_side_effects_possible": False,
        "approval_required": False,
        "reason_codes": ["DEFAULT_CONSERVATIVE"]
    }


⸻

15. Modul-Matching

Ziel

Statt alle Module in den Planner zu geben, werden nur die besten Kandidaten vorgeschlagen.

Anforderungen
	•	Modulranking muss reproduzierbar sein
	•	gleiche Eingabe -> gleiches Ranking
	•	Gründe für jedes Match speichern
	•	Top-N begrenzen, z. B. 5

Pseudocode

def rank_modules(tokens, entities, module_registry):
    ranked = []

    for module in module_registry.list_modules():
        score = 0.0
        reasons = []

        module_name = module.name.lower()
        if module_name in tokens:
            score += 0.50
            reasons.append(f"module_name:{module_name}")

        for kw in module.keywords:
            if kw.lower() in tokens:
                score += 0.20
                reasons.append(f"keyword:{kw.lower()}")

        for entity in entities.systems + entities.services + entities.resources:
            if entity.lower() in [e.lower() for e in module.entities]:
                score += 0.15
                reasons.append(f"entity:{entity.lower()}")

        if score > 0:
            ranked.append({
                "module": module.name,
                "score": min(score, 1.0),
                "reasons": reasons
            })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:5]


⸻

16. Planner-Input-Vertrag

Der Planner bekommt nicht die rohe Useranfrage als primäre Basis, sondern:
	1.	aktuelle Usernachricht
	2.	TaskSketch
	3.	kleine Liste gerankter Module
	4.	letzte 1–2 Userturns
	5.	optional Session-State

Harte Vorgabe

Der Planner darf nur Module aus candidate_modules auswählen, außer wenn explizit planner_decides und ambiguous=true.

⸻

17. Akzeptanzkriterien

Die Implementierung gilt als fertig, wenn:

Funktional
	•	jede Usernachricht vor dem Planner in ein valides TaskSketch transformiert wird
	•	das JSON immer schema-konform ist
	•	keine Tool-Ausführung im Pre-Structurer stattfindet
	•	Top-Kandidatenmodule mit Gründen geliefert werden
	•	Risiko und Intent stabil klassifiziert werden

Qualitätskriterien
	•	gleiche Eingabe erzeugt gleiche TaskSketch
	•	mindestens 90 Prozent der definierten Testfälle liefern erwarteten Intent
	•	mindestens 85 Prozent liefern sinnvolle Kandidatenmodule in Top-3
	•	bei needs_tools=true wird should_avoid_direct_answer=true
	•	bei Diagnosefällen wird bevorzugt explorer empfohlen

Betriebsverhalten
	•	Builder-Laufzeit unter 50 ms bei normaler Eingabe
	•	kein externer API-Call
	•	keine Abhängigkeit von LLM
	•	Debug-Infos optional abschaltbar

⸻

18. Testfälle

Test 1: einfache Wissensfrage

Input:
"Wie funktioniert SafeGuard in Ninko?"

Erwartung:
	•	intent = answer
	•	needs_tools = false
	•	preferred_worker_type = direct_answer
	•	risk = low

⸻

Test 2: Diagnose mehrerer Systeme

Input:
"Mein GitLab spinnt seit dem letzten Deployment, prüf bitte ob PostgreSQL oder der Ingress schuld ist und sag mir den nächsten sicheren Schritt."

Erwartung:
	•	intent = investigate
	•	complexity = compound oder multi_step
	•	needs_tools = true
	•	needs_evidence = true
	•	preferred_worker_type = planner oder explorer
	•	candidate_modules enthält gitlab, postgresql, traefik oder ingress

⸻

Test 3: explizite Aktion

Input:
"Starte den Runner neu und trigger danach die Pipeline."

Erwartung:
	•	intent = act
	•	write_intent_detected = true
	•	approval_required = true
	•	preferred_worker_type = operator
	•	risk mindestens high

⸻

Test 4: Planungsfrage

Input:
"Wie sollte ich die Migration von Traefik v2 auf v3 planen?"

Erwartung:
	•	intent = plan
	•	needs_tools = false
	•	requested_output enthält plan
	•	preferred_worker_type = planner oder direct_answer

⸻

Test 5: unklare Anfrage

Input:
"Kannst du mal danach schauen?"

Erwartung:
	•	intent = unknown oder schwach investigate
	•	ambiguous = true
	•	should_delegate = true
	•	confidence niedrig

⸻

Test 6: K8s-Statusfrage

Input:
"Check bitte im Cluster prod-eu im Namespace billing die Pods nach dem letzten Rollout."

Erwartung:
	•	intent = investigate
	•	domain = kubernetes
	•	entities.clusters = ["prod-eu"]
	•	entities.namespaces = ["billing"]
	•	entities.resources = ["pods"]
	•	candidate_modules enthält kubernetes

⸻

19. Integration in den Orchestrator

Vorher

Orchestrator entscheidet direkt anhand Usertext.

Nachher

Orchestrator ruft zuerst:

task_sketch = task_sketch_builder.build(
    user_message=user_input,
    session_id=session_id,
    conversation_turn_id=turn_id,
    recent_turns=recent_turns
)

Dann Routing grob:

if task_sketch.routing_hints.should_avoid_direct_answer:
    route_away_from_tier1()

if task_sketch.routing_hints.preferred_worker_type == "explorer":
    delegate_to_explorer(task_sketch)

elif task_sketch.routing_hints.preferred_worker_type == "planner":
    delegate_to_planner(task_sketch)

elif task_sketch.routing_hints.preferred_worker_type == "operator":
    delegate_to_operator(task_sketch)

else:
    direct_answer(task_sketch)


⸻

20. Logging und Observability

Jeder TaskSketch-Build soll optional loggen:
	•	session_id
	•	turn_id
	•	intent
	•	complexity
	•	risk
	•	top_modules
	•	confidence
	•	matched_rules

Nicht loggen:
	•	Secrets
	•	sensible Rohdaten unmaskiert

⸻

21. Erweiterbarkeit

Die Vor-Strukturierung muss leicht um neue Domains erweiterbar sein.

Erweiterungspunkte
	•	neue Intent-Regeln
	•	neue Risiko-Regeln
	•	neue Modul-Metadaten
	•	neue Entitätstypen
	•	neue Domain-Mappings
	•	sprachspezifische Synonyme

⸻

22. Was der Coding-Agent konkret bauen soll

Arbeitsauftrag

Implementiere eine neue Komponente DeterministicTaskSketchBuilder, die vor jedem Planner- oder Routing-Schritt aus einer User-Anfrage ein deterministisches, schema-valide TaskSketch erzeugt.

Muss enthalten
	•	Normalisierung des Inputs
	•	regelbasierte Intent-Erkennung
	•	deterministische Ziel-Extraktion
	•	Komplexitätserkennung
	•	Risikoermittlung
	•	Entitäten-Extraktion
	•	Modulranking auf Basis vorhandener Modul-Metadaten
	•	Routing-Hints
	•	Unsicherheitskennzeichnung
	•	Pydantic-Schema
	•	Unit-Tests für mindestens 10 repräsentative Fälle
	•	Integration in den aktuellen Orchestrator vor dem Planner

Muss explizit vermieden werden
	•	keine LLM-Nutzung in dieser Komponente
	•	keine Tool-Calls
	•	keine freie Textplanung
	•	keine finale Aktionsausführung
	•	kein verstecktes Fallback auf probabilistische Klassifikation

⸻

23. Empfohlene Implementierungsreihenfolge
	1.	Pydantic-Schemas bauen
	2.	Input-Normalisierung
	3.	Intent-Regeln
	4.	Risiko-Regeln
	5.	Entity-Extraktion
	6.	Modulranking
	7.	Routing-Hints
	8.	JSON-Builder
	9.	Tests
	10.	Integration in Orchestrator
	11.	Debug/Telemetry

⸻

24. Definition of done

Fertig ist die Änderung, wenn:
	•	alle Requests vor Planner/Routing ein TaskSketch bekommen
	•	Planner mit TaskSketch statt mit rohem Usertext arbeitet
	•	mindestens 10 Unit-Tests grün sind
	•	mindestens 3 Integrationsfälle mit Orchestrator funktionieren
	•	Routing bei Diagnosefällen seltener direkt in Tier 1 landet
	•	die Ausgabe reproduzierbar ist

⸻

25. Kurzprompt für deinen Coding-Agent

Du kannst ihm zusätzlich das hier geben:

Baue eine neue deterministische Vorverarbeitungsschicht vor dem Planner namens `DeterministicTaskSketchBuilder`.

Ziel:
Aus jeder User-Anfrage soll ohne LLM und ohne Tool-Ausführung ein strukturiertes `TaskSketch` als Pydantic-Objekt erzeugt werden. Dieses enthält mindestens:
- intent
- primary_goal
- secondary_goals
- requested_output
- complexity
- needs_tools
- needs_fresh_state
- needs_evidence
- risk
- candidate_modules_ranked
- entities
- routing_hints
- uncertainty
- debug

Wichtige Regeln:
- deterministisch, reproduzierbar
- kein freier Text als Endprodukt, nur strukturiertes JSON/Pydantic
- keine LLM-Aufrufe
- keine Tool-Ausführung
- gleiche Eingabe -> gleiche Ausgabe
- Top-Module per Score und mit Begründung ranken
- Diagnosefälle sollen `should_avoid_direct_answer=true` setzen
- explizite Write-Requests müssen Risiko und Approval markieren

Bitte implementiere:
- Pydantic-Schemas
- Normalizer
- Rule-based intent detection
- Risk inference
- Entity extraction
- Module ranking against module metadata
- Routing hint inference
- Unit tests
- Integration in den Orchestrator vor dem Planner

Nutze eine klare Dateistruktur, möglichst unter `core/prestructure/`.


⸻

Wenn du willst, mache ich dir im nächsten Schritt noch die konkrete Planner-JSON-Spezifikation, die direkt auf diesem TaskSketch aufbaut.