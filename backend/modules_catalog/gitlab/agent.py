"""GitLab module agent."""

from agents.base_agent import BaseAgent
from modules_catalog.gitlab import tools

GITLAB_SYSTEM_PROMPT = """You are Ninko's GitLab CI/CD specialist.

Capabilities:
- Manage repositories and projects.
- Create and monitor pipelines.
- Manage merge requests, releases, tags, CI/CD variables, and schedules.

Tool execution rules:
- Use the available GitLab tools to query and control GitLab data.
- For pipeline questions, inspect pipelines or jobs before answering.
- For scheduled pipeline requests, use the schedule-specific tools.

Output format:
- For lists (Projects, MRs, Issues, Pipelines, Variables): ALWAYS use Markdown tables.
- Example: | Name | Branch | Status |
- NEVER return raw JSON or Python repr as the final answer.
- Always include units for numbers.
- Color-code status when helpful.

Safety and confirmation rules:
- Ask for confirmation before destructive or irreversible project changes.
- Treat variables carefully and never reveal secret values.

Error handling:
- If a tool fails, explain the concrete GitLab API, permission, or project issue."""


class GitLabAgent(BaseAgent):
    """GitLab CI/CD specialist agent."""

    name = "gitlab"
    description = {
        "de": "GitLab CI/CD – Repositories, Pipelines, Jobs, Merge Requests und Releases",
        "en": "GitLab CI/CD – Repositories, Pipelines, Jobs, Merge Requests and Releases",
        "fr": "GitLab CI/CD – Dépôts, Pipelines, Jobs, Merge Requests et Releases",
        "es": "GitLab CI/CD – Repositorios, Pipelines, Jobs, Merge Requests y Releases",
        "it": "GitLab CI/CD – Repository, Pipeline, Job, Merge Request e Release",
        "nl": "GitLab CI/CD – Repositories, Jobs, Merge Requests en Releases",
        "pl": "GitLab CI/CD – Repozytoria, Pipeline'y, Zadania, Merge Requesty i Release'y",
        "pt": "GitLab CI/CD – Repositórios, Pipelines, Jobs, Merge Requests e Releases",
        "ja": "GitLab CI/CD – リポジトリ、パイプラインジョブ、マージリクエスト、リリース",
        "zh": "GitLab CI/CD – 仓库、流水线、任务、合并请求和发布",
    }

    def __init__(self) -> None:
        """Initialize the GitLab agent."""
        super().__init__(
            name="gitlab",
            system_prompt=GITLAB_SYSTEM_PROMPT,
            tools=[
                tools.get_gitlab_status,
                tools.list_gitlab_projects,
                tools.get_gitlab_project,
                tools.list_gitlab_pipelines,
                tools.get_gitlab_pipeline,
                tools.trigger_gitlab_pipeline,
                tools.cancel_gitlab_pipeline,
                tools.retry_gitlab_pipeline,
                tools.list_gitlab_jobs,
                tools.get_gitlab_job_log,
                tools.list_gitlab_merge_requests,
                tools.get_gitlab_merge_request,
                tools.create_gitlab_merge_request,
                tools.accept_gitlab_merge_request,
                tools.list_gitlab_branches,
                tools.list_gitlab_commits,
                tools.list_gitlab_tags,
                tools.create_gitlab_release,
                tools.list_gitlab_variables,
                tools.create_gitlab_variable,
                tools.delete_gitlab_variable,
                tools.get_gitlab_pipeline_schedules,
                tools.create_gitlab_pipeline_schedule,
                tools.trigger_gitlab_pipeline_schedule,
            ],
        )


agent = GitLabAgent()
