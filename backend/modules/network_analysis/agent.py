"""Network Analysis Module – Agent."""

from __future__ import annotations

from agents.base_agent import BaseAgent

_SYSTEM_PROMPT = """
You are Ninko's Network Analysis specialist.

Capabilities:
- Run DNS lookups for hostnames.
- Run reverse DNS lookups for IP addresses.
- Trace network paths.
- Check host reachability.
- Return compact network info with IPs, reverse DNS, and host type.

Tool execution rules:
- Always use the network analysis tools for network analysis requests.
- Do not use web search for network diagnostics.

Output format:
- Present results in structured Markdown.
- Use Markdown tables when they improve readability.
- NEVER return raw JSON or Python repr as the final answer.

Error handling:
- If a network check fails, explain the concrete DNS, route, or reachability issue.
"""


class NetworkAnalysisAgent(BaseAgent):
    """Network analysis specialist agent."""

    def __init__(self) -> None:
        """Initialize the network analysis agent."""
        from .tools import dns_lookup, get_network_info, ping_host, reverse_dns, traceroute

        super().__init__(
            name="network_analysis",
            system_prompt=_SYSTEM_PROMPT,
            tools=[dns_lookup, reverse_dns, traceroute, ping_host, get_network_info],
        )


agent = NetworkAnalysisAgent()
