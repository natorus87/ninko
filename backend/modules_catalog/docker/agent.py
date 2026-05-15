"""Docker module specialist agent for Docker host management."""

from __future__ import annotations

from agents.base_agent import BaseAgent

from .tools import (
    get_container_logs,
    get_container_stats,
    get_docker_disk_usage,
    get_docker_info,
    get_docker_version,
    inspect_container,
    list_containers,
    list_images,
    list_volumes,
    pull_image,
    remove_container,
    remove_image,
    remove_volume,
    restart_container,
    start_container,
    stop_container,
)

DOCKER_SYSTEM_PROMPT = """You are Ninko's Docker specialist.

Capabilities:
- Container management: list, start, stop, restart, remove
- Container logs and resource statistics (CPU, RAM, network)
- Image management: list, pull, remove
- Volume management: list, remove
- System info: Docker version, storage usage, host resources

Tool execution rules:
- Call Docker tools to answer status, overview, or log questions — never rely on general knowledge.
- Check the current container status before performing actions.

Output format:
- For lists (Containers, Images, Volumes): ALWAYS use Markdown tables.
- Example header: | Name | Image | Status | Ports |
- NEVER return bullet lists, plain text, or raw JSON.
- Always include units for sizes (%, GB, MB).
- When listing containers, indicate status clearly (running, stopped, exited).
- Color-code status when helpful (running=green, exited=red).

Safety and confirmation rules:
- Destructive actions (remove container, force remove) require explicit confirmation.
- Image removal with force=true requires confirmation.
- Be precise and security-conscious.

Error handling:
- If a tool call fails, surface the Docker error verbatim and suggest a concrete next step.
- Warn on high resource utilization."""


class DockerAgent(BaseAgent):
    """Docker specialist with all Docker management tools."""

    def __init__(self) -> None:
        """Initialize the Docker agent."""
        super().__init__(
            name="docker",
            system_prompt=DOCKER_SYSTEM_PROMPT,
            tools=[
                list_containers,
                inspect_container,
                start_container,
                stop_container,
                restart_container,
                remove_container,
                get_container_logs,
                get_container_stats,
                list_images,
                pull_image,
                remove_image,
                list_volumes,
                remove_volume,
                get_docker_info,
                get_docker_version,
                get_docker_disk_usage,
            ],
        )
