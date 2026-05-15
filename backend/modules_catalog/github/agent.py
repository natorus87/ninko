"""GitHub module agent."""

from agents.base_agent import BaseAgent

from . import tools

GITHUB_SYSTEM_PROMPT = """You are Ninko's GitHub specialist.

Capabilities:
- Manage repositories and repository content.
- Create and monitor GitHub Actions workflows and runs.
- Manage pull requests, issues, releases, tags, variables, and secrets.
- Search code and issues across repositories.

Tool execution rules:
- Use the available GitHub tools to query and control GitHub data.
- For workflow questions, inspect workflows or runs before answering.
- For code or issue searches, use the dedicated search tools.

Output format:
- For lists (Repos, Issues, PRs, Actions, Releases): ALWAYS use Markdown tables.
- Example: | Name | Stars | Language |
- NEVER return raw JSON or Python repr as the final answer.
- Always include units for numbers.
- Color-code status when helpful.

Safety and confirmation rules:
- Ask for confirmation before destructive or irreversible repository changes.
- Treat secrets carefully and never reveal secret values.

Error handling:
- If a tool fails, explain the concrete GitHub API, permission, or repository issue."""


class GitHubAgent(BaseAgent):
    """GitHub specialist agent."""

    name = "github"
    description = {
        "de": "GitHub – Repositories, Actions, Pull Requests, Issues und Releases",
        "en": "GitHub – Repositories, Actions, Pull Requests, Issues and Releases",
        "fr": "GitHub – Dépôts, Actions, Pull Requests, Issues et Releases",
        "es": "GitHub – Repositorios, Actions, Pull Requests, Issues y Releases",
        "it": "GitHub – Repository, Actions, Pull Request, Issue e Release",
        "nl": "GitHub – Repositories, Actions, Pull Requests, Issues en Releases",
        "pl": "GitHub – Repozytoria, Actions, Pull Requesty, Issues i Releases",
        "pt": "GitHub – Repositórios, Actions, Pull Requests, Issues e Releases",
        "ja": "GitHub – リポジトリ、アクションプルリクエスト、イシュー、リリース",
        "zh": "GitHub – 仓库、Actions、Pull Requests、问题和发布",
    }

    def __init__(self) -> None:
        """Initialize the GitHub agent."""
        super().__init__(
            name="github",
            system_prompt=GITHUB_SYSTEM_PROMPT,
            tools=[
                tools.get_github_status,
                tools.list_github_repos,
                tools.get_github_repo,
                tools.list_github_workflows,
                tools.list_github_workflow_runs,
                tools.get_github_workflow_run,
                tools.trigger_github_workflow,
                tools.cancel_github_workflow_run,
                tools.rerun_github_workflow,
                tools.list_github_jobs,
                tools.get_github_job_logs,
                tools.list_github_pull_requests,
                tools.get_github_pull_request,
                tools.create_github_pull_request,
                tools.merge_github_pull_request,
                tools.list_github_issues,
                tools.create_github_issue,
                tools.list_github_branches,
                tools.list_github_commits,
                tools.list_github_tags,
                tools.list_github_releases,
                tools.create_github_release,
                tools.list_github_variables,
                tools.create_github_variable,
                tools.delete_github_variable,
                tools.list_github_secrets,
                tools.get_github_repo_content,
                tools.search_github_code,
                tools.search_github_issues,
            ],
        )


agent = GitHubAgent()
