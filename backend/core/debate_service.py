"""
Multi-Agent Debate System for Ninko.

Supports structured debates with roles (primary, critic, judge) and voting.
Three modes: auto_consensus, tribunal, symposion.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Any

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from core.llm_factory import get_llm

logger = logging.getLogger("ninko.debate")

DebateMode = Literal["auto_consensus", "tribunal", "symposion"]
DebateRole = Literal["primary", "critic", "judge", "observer"]


@dataclass
class DebateParticipant:
    agent_id: str
    role: DebateRole
    name: str
    system_prompt_addon: str = ""
    history: list[dict] = field(default_factory=list)
    votes_received: int = 0
    is_active: bool = True


@dataclass
class DebateRound:
    round_number: int
    contributions: list[dict] = field(default_factory=list)
    consensus_reached: bool = False
    summary: str = ""


@dataclass
class DebateState:
    debate_id: str
    topic: str
    mode: DebateMode
    participants: list[DebateParticipant] = field(default_factory=list)
    rounds: list[DebateRound] = field(default_factory=list)
    current_round: int = 0
    max_rounds: int = 5
    consensus_threshold: float = 0.7
    final_decision: str = ""
    status: Literal["running", "consensus", "deadlock", "completed"] = "running"
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None


_DEBATE_TTL_SECONDS = 7 * 24 * 3600  # 7 Tage TTL für abgeschlossene Debates


class DebateService:
    def __init__(self, redis, orchestrator, llm_factory):
        self.redis = redis
        self.orchestrator = orchestrator
        self.llm_factory = llm_factory
        self._active_debates: dict[str, DebateState] = {}
        self._votes_cast: dict[str, set[tuple[str, str]]] = {}

    async def create_debate(
        self,
        topic: str,
        mode: DebateMode,
        participant_configs: list[dict],
        max_rounds: int = 5,
        consensus_threshold: float = 0.7,
        tenant_id: str = "default",
    ) -> DebateState:
        debate_id = f"debate_{uuid.uuid4().hex}"

        participants = [
            DebateParticipant(
                agent_id=config["agent_id"][:128],
                role=config.get("role", "observer"),
                name=re.sub(r"[^\w\s\-]", "", config.get("name", config["agent_id"]))[:64],
                system_prompt_addon="",
            )
            for config in participant_configs
        ]

        debate = DebateState(
            debate_id=debate_id,
            topic=topic,
            mode=mode,
            participants=participants,
            max_rounds=max_rounds,
            consensus_threshold=consensus_threshold,
        )

        self._active_debates[debate_id] = debate
        await self._persist_debate(debate, tenant_id)

        logger.info(
            "Debate created: id=%s mode=%s participants=%d max_rounds=%d",
            debate_id,
            mode,
            len(participants),
            max_rounds,
        )

        return debate

    async def run_debate_round(self, debate_id: str, tenant_id: str = "default") -> DebateRound:
        debate = self._active_debates.get(debate_id)
        if not debate:
            debate = await self._load_debate(debate_id, tenant_id)
            if not debate:
                raise ValueError(f"Debate {debate_id} not found")
            self._active_debates[debate_id] = debate

        debate.current_round += 1
        current_round = DebateRound(round_number=debate.current_round)

        logger.debug(
            "Starting debate round %d/%d for %s", debate.current_round, debate.max_rounds, debate_id
        )

        active_participants = [p for p in debate.participants if p.is_active]

        contributions = await asyncio.gather(
            *[
                self._get_participant_contribution(debate, p, current_round.round_number)
                for p in active_participants
            ],
            return_exceptions=True,
        )

        for participant, contribution_result in zip(active_participants, contributions):
            if isinstance(contribution_result, Exception):
                logger.error(
                    "Participant %s failed in round %d: %s",
                    participant.name,
                    debate.current_round,
                    contribution_result,
                )
                contribution: dict = {
                    "participant_name": participant.name,
                    "participant_role": participant.role,
                    "agent_id": participant.agent_id,
                    "content": f"[Error: {contribution_result}]",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            else:
                contribution = contribution_result  # type: ignore

            current_round.contributions.append(contribution)

            participant.history.append(
                {
                    "role": "assistant",
                    "content": contribution["content"],
                    "round": debate.current_round,
                }
            )

            for other in debate.participants:
                if other.agent_id != participant.agent_id and other.is_active:
                    other.history.append(
                        {
                            "role": "user",
                            "name": participant.name,
                            "content": f"[{participant.role.upper()}] {participant.name}: {contribution['content']}",
                            "round": debate.current_round,
                        }
                    )

        debate.rounds.append(current_round)

        if debate.mode == "auto_consensus":
            current_round.consensus_reached = await self._check_consensus(debate, current_round)
            if current_round.consensus_reached:
                debate.status = "consensus"
                debate.final_decision = await self._synthesize_consensus(debate)
                debate.finished_at = datetime.now(timezone.utc).isoformat()
        elif debate.mode == "tribunal":
            if debate.current_round >= debate.max_rounds:
                debate.final_decision = await self._judge_decision(debate)
                debate.status = "completed"
                debate.finished_at = datetime.now(timezone.utc).isoformat()

        await self._persist_debate(debate, tenant_id)

        return current_round

    async def run_full_debate(self, debate_id: str, tenant_id: str = "default") -> DebateState:
        debate = self._active_debates.get(debate_id)
        if not debate:
            debate = await self._load_debate(debate_id, tenant_id)
            if not debate:
                raise ValueError(f"Debate {debate_id} not found")
            self._active_debates[debate_id] = debate

        max_iterations = debate.max_rounds * 2
        iteration = 0

        while (
            debate.status == "running"
            and iteration < max_iterations
            and debate.current_round < debate.max_rounds
        ):
            await self.run_debate_round(debate_id, tenant_id)
            iteration += 1

            if debate.mode == "symposion" and debate.current_round >= debate.max_rounds:
                debate.status = "completed"
                debate.final_decision = await self._synthesize_symposion(debate)
                debate.finished_at = datetime.now(timezone.utc).isoformat()
                await self._persist_debate(debate, tenant_id)
                break

        if debate.status == "running":
            if debate.mode == "auto_consensus":
                debate.status = "deadlock"
                debate.final_decision = await self._synthesize_deadlock(debate)
            debate.finished_at = datetime.now(timezone.utc).isoformat()
            await self._persist_debate(debate, tenant_id)

        return debate

    async def _get_participant_contribution(
        self, debate: DebateState, participant: DebateParticipant, round_number: int
    ) -> dict:
        role_instructions = self._get_role_instructions(participant.role)

        messages = [
            SystemMessage(
                content=f"""You are participating in a structured debate.

Topic: {debate.topic}
Your Role: {participant.role.upper()} ({participant.name})
Round: {round_number}/{debate.max_rounds}

{role_instructions}

{participant.system_prompt_addon}
"""
            )
        ]

        for msg in participant.history:
            if msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
            elif msg["role"] == "user":
                messages.append(HumanMessage(content=msg.get("content", "")))

        if round_number == 1:
            prompt = f"Please present your opening position on '{debate.topic}'."
        else:
            prompt = f"Please respond to the previous contributions in round {round_number}."

        messages.append(HumanMessage(content=prompt))

        try:
            if self.orchestrator:
                chat_history = []
                for msg in messages[:-1]:
                    if isinstance(msg, HumanMessage):
                        chat_history.append({"role": "user", "content": msg.content})
                    elif isinstance(msg, AIMessage):
                        chat_history.append({"role": "assistant", "content": msg.content})

                force_target = (
                    participant.agent_id
                    if not participant.agent_id.startswith("orchestrator")
                    else None
                )

                response_text, _, _ = await self.orchestrator.route(
                    message=prompt,
                    chat_history=chat_history,
                    session_id=f"{debate.debate_id}_{participant.agent_id}",
                    force_module=force_target,
                )
            else:
                llm = get_llm()
                response = await llm.ainvoke(messages)
                response_text = str(response.content)

            return {
                "participant_name": participant.name,
                "participant_role": participant.role,
                "agent_id": participant.agent_id,
                "content": response_text,
                "round": round_number,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as exc:
            logger.error("Failed to get contribution from %s: %s", participant.name, exc)
            raise

    def _get_role_instructions(self, role: DebateRole) -> str:
        instructions = {
            "primary": """You are the Primary Agent. Represent a clear position.
- Present structured arguments
- Use facts and logic
- Respond to criticism constructively""",
            "critic": """You are the Critic. Challenge all positions rigorously.
- Identify logical errors and weaknesses
- Demand evidence for claims
- Offer constructive alternatives""",
            "judge": """You are the Judge. Evaluate all arguments neutrally.
- Be fair and impartial
- Consider all sides equally
- Ultimately make a reasoned decision""",
            "observer": """You are an Observer. Enrich the debate with additional perspectives.
- Ask clarifying questions
- Bring in alternative viewpoints
- Remain respectful and constructive""",
        }
        return instructions.get(role, instructions["observer"])

    async def _check_consensus(self, debate: DebateState, current_round: DebateRound) -> bool:
        if len(current_round.contributions) < 2:
            return False

        contents = [c["content"] for c in current_round.contributions]
        combined = "\n\n===\n\n".join(contents)

        prompt = f"""Analyze these debate contributions for consensus:

Topic: {debate.topic}

Contributions:
{combined}

Questions:
1. Are the positions fundamentally compatible or contradictory?
2. Are there common underlying assumptions?
3. Is a practical middle ground visible?

Respond ONLY with a JSON object:
{{"consensus_reached": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}}"""

        try:
            llm = get_llm()
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            result_text = response.content.strip()

            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            result = json.loads(result_text)
            consensus = result.get("consensus_reached", False)
            confidence = result.get("confidence", 0.0)

            logger.debug("Consensus check: reached=%s confidence=%.2f", consensus, confidence)

            return consensus and confidence >= debate.consensus_threshold

        except Exception as exc:
            logger.error("Consensus check failed: %s", exc)
            return False

    async def _synthesize_consensus(self, debate: DebateState) -> str:
        all_contributions = []
        for r in debate.rounds:
            for c in r.contributions:
                all_contributions.append(
                    f"[{c['participant_role']}] {c['participant_name']}: {c['content']}"
                )

        combined = "\n\n".join(all_contributions)

        prompt = f"""Synthesize a consensus from this debate:

Topic: {debate.topic}

Debate History:
{combined}

Create a concise summary (3-5 sentences) that:
- Represents the shared position
- Includes the key reasoning
- Names concrete next steps"""

        try:
            llm = get_llm()
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            return str(response.content).strip()
        except Exception as exc:
            logger.error("Consensus synthesis failed: %s", exc)
            return f"Consensus reached (summary error: {exc})"

    async def _synthesize_deadlock(self, debate: DebateState) -> str:
        all_contributions = []
        for r in debate.rounds:
            for c in r.contributions:
                all_contributions.append(
                    f"[{c['participant_role']}] {c['participant_name']}: {c['content']}"
                )

        combined = "\n\n".join(all_contributions)

        prompt = f"""This debate ended without consensus. Summarize the deadlock:

Topic: {debate.topic}

Debate History:
{combined}

Describe:
1. The different positions
2. The central conflict points
3. Recommended next steps for conflict resolution"""

        try:
            llm = get_llm()
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            return str(response.content).strip()
        except Exception as exc:
            logger.error("Deadlock synthesis failed: %s", exc)
            return f"No consensus reached (after {debate.max_rounds} rounds)"

    async def _judge_decision(self, debate: DebateState) -> str:
        judge = next((p for p in debate.participants if p.role == "judge" and p.is_active), None)
        if not judge:
            return "No judge available for decision"

        all_contributions = []
        for r in debate.rounds:
            for c in r.contributions:
                all_contributions.append(
                    f"[{c['participant_role']}] {c['participant_name']}: {c['content']}"
                )

        combined = "\n\n".join(all_contributions)

        prompt = f"""As Judge, render a fair decision based on this debate:

Topic: {debate.topic}

Debate History:
{combined}

Please render your verdict:
1. Which position is better supported?
2. What is the fair decision?
3. How should it be implemented?"""

        try:
            chat_history = []
            for msg in judge.history:
                if msg["role"] == "assistant":
                    chat_history.append({"role": "assistant", "content": msg["content"]})
                elif msg["role"] == "user":
                    chat_history.append({"role": "user", "content": msg.get("content", "")})

            if self.orchestrator:
                response_text, _, _ = await self.orchestrator.route(
                    message=prompt,
                    chat_history=chat_history,
                    session_id=f"{debate.debate_id}_{judge.agent_id}_decision",
                    force_module=judge.agent_id
                    if not judge.agent_id.startswith("orchestrator")
                    else None,
                )
            else:
                llm = get_llm()
                messages = [SystemMessage(content=self._get_role_instructions("judge"))]
                for h in judge.history:
                    if h["role"] == "assistant":
                        messages.append(AIMessage(content=h["content"]))
                    elif h["role"] == "user":
                        messages.append(HumanMessage(content=h.get("content", "")))
                messages.append(HumanMessage(content=prompt))
                response = await llm.ainvoke(messages)
                response_text = str(response.content)

            return response_text.strip()

        except Exception as exc:
            logger.error("Judge decision failed: %s", exc)
            return f"Decision failed: {exc}"

    async def _synthesize_symposion(self, debate: DebateState) -> str:
        all_contributions = []
        for r in debate.rounds:
            for c in r.contributions:
                all_contributions.append(
                    f"[{c['participant_role']}] {c['participant_name']}: {c['content']}"
                )

        combined = "\n\n".join(all_contributions)

        prompt = f"""Create a thematic summary of this symposium:

Topic: {debate.topic}

Discussion History:
{combined}

Describe:
1. The various perspectives and insights
2. Common themes and contrasts
3. Open questions for further discussion"""

        try:
            llm = get_llm()
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            return str(response.content).strip()
        except Exception as exc:
            logger.error("Symposion synthesis failed: %s", exc)
            return f"Symposion completed (summary error: {exc})"

    async def _persist_debate(self, debate: DebateState, tenant_id: str) -> None:
        key = f"ninko:debates:{tenant_id}:{debate.debate_id}"
        data = {
            "debate_id": debate.debate_id,
            "topic": debate.topic,
            "mode": debate.mode,
            "participants": [
                {
                    "agent_id": p.agent_id,
                    "role": p.role,
                    "name": p.name,
                    "history": p.history,
                    "votes_received": p.votes_received,
                    "is_active": p.is_active,
                }
                for p in debate.participants
            ],
            "rounds": [
                {
                    "round_number": r.round_number,
                    "contributions": r.contributions,
                    "consensus_reached": r.consensus_reached,
                    "summary": r.summary,
                }
                for r in debate.rounds
            ],
            "current_round": debate.current_round,
            "max_rounds": debate.max_rounds,
            "consensus_threshold": debate.consensus_threshold,
            "final_decision": debate.final_decision,
            "status": debate.status,
            "started_at": debate.started_at,
            "finished_at": debate.finished_at,
        }
        await self.redis.connection.set(key, json.dumps(data))
        if debate.status in ("consensus", "completed", "deadlock"):
            await self.redis.connection.expire(key, _DEBATE_TTL_SECONDS)

        index_key = f"ninko:debates:{tenant_id}:index"
        index_raw = await self.redis.connection.get(index_key)
        index = json.loads(index_raw) if index_raw else []
        if debate.debate_id not in index:
            index.append(debate.debate_id)
            await self.redis.connection.set(index_key, json.dumps(index))

    async def _load_debate(self, debate_id: str, tenant_id: str) -> DebateState | None:
        key = f"ninko:debates:{tenant_id}:{debate_id}"
        data_raw = await self.redis.connection.get(key)
        if not data_raw:
            return None

        try:
            data = json.loads(data_raw)
            debate = DebateState(
                debate_id=data["debate_id"],
                topic=data["topic"],
                mode=data["mode"],
                participants=[
                    DebateParticipant(
                        agent_id=p["agent_id"],
                        role=p["role"],
                        name=p["name"],
                        history=p.get("history", []),
                        votes_received=p.get("votes_received", 0),
                        is_active=p.get("is_active", True),
                    )
                    for p in data["participants"]
                ],
                rounds=[
                    DebateRound(
                        round_number=r["round_number"],
                        contributions=r.get("contributions", []),
                        consensus_reached=r.get("consensus_reached", False),
                        summary=r.get("summary", ""),
                    )
                    for r in data.get("rounds", [])
                ],
                current_round=data.get("current_round", 0),
                max_rounds=data.get("max_rounds", 5),
                consensus_threshold=data.get("consensus_threshold", 0.7),
                final_decision=data.get("final_decision", ""),
                status=data.get("status", "running"),
                started_at=data.get("started_at", ""),
                finished_at=data.get("finished_at"),
            )
            return debate
        except Exception as exc:
            logger.error("Failed to load debate %s: %s", debate_id, exc)
            return None

    def get_debate_status(self, debate_id: str) -> DebateState | None:
        return self._active_debates.get(debate_id)

    async def list_debates(self, tenant_id: str = "default") -> list[dict]:
        index_key = f"ninko:debates:{tenant_id}:index"
        index_raw = await self.redis.connection.get(index_key)
        debate_ids = json.loads(index_raw) if index_raw else []

        loaded = await asyncio.gather(
            *[self._load_debate(did, tenant_id) for did in debate_ids]
        )
        return [
            {
                "debate_id": d.debate_id,
                "topic": d.topic,
                "mode": d.mode,
                "status": d.status,
                "current_round": d.current_round,
                "max_rounds": d.max_rounds,
                "started_at": d.started_at,
                "finished_at": d.finished_at,
            }
            for d in loaded
            if d is not None
        ]

    async def vote(
        self, debate_id: str, voter_agent_id: str, target_agent_id: str, tenant_id: str = "default"
    ) -> bool:
        debate = self._active_debates.get(debate_id)
        if not debate:
            debate = await self._load_debate(debate_id, tenant_id)
            if not debate:
                return False
            self._active_debates[debate_id] = debate

        voter = next((p for p in debate.participants if p.agent_id == voter_agent_id), None)
        if not voter or not voter.is_active:
            return False

        target = next((p for p in debate.participants if p.agent_id == target_agent_id), None)
        if not target:
            return False

        vote_key = (voter_agent_id, target_agent_id)
        cast = self._votes_cast.setdefault(debate_id, set())
        if vote_key in cast:
            return False
        cast.add(vote_key)

        target.votes_received += 1
        await self._persist_debate(debate, tenant_id)

        logger.info(
            "Vote recorded: %s voted for %s in %s", voter_agent_id, target_agent_id, debate_id
        )
        return True

    async def get_debate_result(self, debate_id: str, tenant_id: str = "default") -> dict | None:
        debate = self._active_debates.get(debate_id)
        if not debate:
            debate = await self._load_debate(debate_id, tenant_id)

        if not debate:
            return None

        return {
            "debate_id": debate.debate_id,
            "topic": debate.topic,
            "mode": debate.mode,
            "status": debate.status,
            "participants": [
                {
                    "agent_id": p.agent_id,
                    "role": p.role,
                    "name": p.name,
                    "votes_received": p.votes_received,
                    "is_active": p.is_active,
                }
                for p in debate.participants
            ],
            "rounds": [
                {
                    "round_number": r.round_number,
                    "contributions": r.contributions,
                    "consensus_reached": r.consensus_reached,
                }
                for r in debate.rounds
            ],
            "final_decision": debate.final_decision,
            "current_round": debate.current_round,
            "max_rounds": debate.max_rounds,
            "started_at": debate.started_at,
            "finished_at": debate.finished_at,
        }
