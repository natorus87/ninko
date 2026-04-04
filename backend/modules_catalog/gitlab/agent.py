"""GitLab module agent."""

from typing import Optional

from agents.base_agent import BaseAgent
from modules_catalog.gitlab import tools
from modules_catalog.gitlab.manifest import module_manifest


class GitLabAgent(BaseAgent):
    """GitLab CI/CD Agent."""

    name = "gitlab"
    description = {
        "de": "GitLab CI/CD – Repositories, Pipelines, Jobs, Merge Requests und Releases",
        "en": "GitLab CI/CD – Repositories, Pipelines, Jobs, Merge Requests and Releases",
        "fr": "GitLab CI/CD – Dépôts, Pipelines, Jobs, Merge Requests et Releases",
        "es": "GitLab CI/CD – Repositorios, Pipelines, Jobs, Merge Requests y Releases",
        "it": "GitLab CI/CD – Repository, Pipeline, Job, Merge Request e Release",
        "nl": "GitLab CI/CD – Repositories, Pipelines, Jobs, Merge Requests en Releases",
        "pl": "GitLab CI/CD – Repozytoria, Pipeline'y, Zadania, Merge Requesty i Release'y",
        "pt": "GitLab CI/CD – Repositórios, Pipelines, Jobs, Merge Requests e Releases",
        "ja": "GitLab CI/CD – リポジトリ、パイプラインジョブ、マージリクエスト、リリース",
        "zh": "GitLab CI/CD – 仓库、流水线、任务、合并请求和发布",
    }
    system_prompt = {
        "de": """Du bist ein GitLab CI/CD-Experte. Du hilfst Benutzern bei:
- Verwaltung von Repositories und Projekten
- Erstellung und Überwachung von Pipelines
- Verwaltung von Merge Requests
- Erstellung von Releases und Tags
- Verwaltung von CI/CD-Variablen
- Pipeline-Schedules und Cron-Jobs

Verwende die verfügbaren Tools, um GitLab-Daten abzufragen und zu steuern.
Antworte in Deutsch.""",
        "en": """You are a GitLab CI/CD expert. You help users with:
- Managing repositories and projects
- Creating and monitoring pipelines
- Managing merge requests
- Creating releases and tags
- Managing CI/CD variables
- Pipeline schedules and cron jobs

Use the available tools to query and control GitLab data.
Respond in English.""",
        "fr": """Vous êtes un expert GitLab CI/CD. Vous aidez les utilisateurs avec:
- Gestion des dépôts et projets
- Création et surveillance des pipelines
- Gestion des merge requests
- Création de releases et tags
- Gestion des variables CI/CD
- Plansification des pipelines et jobs cron

Utilisez les outils disponibles pour interroger et contrôler les données GitLab.
Répondez en français.""",
        "es": """Eres un experto en GitLab CI/CD. Ayudas a los usuarios con:
- Gestión de repositorios y proyectos
- Creación y monitoreo de pipelines
- Gestión de merge requests
- Creación de releases y tags
- Gestión de variables CI/CD
- Programación de pipelines y trabajos cron

Usa las herramientas disponibles para consultar y controlar datos de GitLab.
Responde en español.""",
        "it": """Sei un esperto di GitLab CI/CD. Aiuti gli utenti con:
- Gestione di repository e progetti
- Creazione e monitoraggio delle pipeline
- Gestione delle merge request
- Creazione di release e tag
- Gestione delle variabili CI/CD
- Schedule delle pipeline e job cron

Usa gli strumenti disponibili per interrogare e controllare i dati GitLab.
Rispondi in italiano.""",
        "nl": """Je bent een GitLab CI/CD-expert. Je helpt gebruikers met:
- Beheer van repositories en projecten
- Maken en monitoren van pipelines
- Beheer van merge requests
- Maken van releases en tags
- Beheer van CI/CD-variabelen
- Pipeline-schedules en cron-jobs

Gebruik de beschikbare tools om GitLab-gegevens te raadplegen en te sturen.
Antwoord in het Nederlands.""",
        "pl": """Jesteś ekspertem GitLab CI/CD. Pomagasz użytkownikom z:
- Zarządzaniem repozytoriami i projektami
- Tworzeniem i monitorowaniem pipeline'ów
- Zarządzaniem merge requestami
- Tworzeniem release'ów i tagów
- Zarządzaniem zmiennymi CI/CD
- Harmonogramami pipeline'ów i zadaniami cron

Użyj dostępnych narzędzi do wykonywania zapytań i kontrolowania danych GitLab.
Odpowiedz po polsku.""",
        "pt": """Você é um especialista em GitLab CI/CD. Você ajuda os usuários com:
- Gerenciamento de repositórios e projetos
- Criação e monitoramento de pipelines
- Gerenciamento de merge requests
- Criação de releases e tags
- Gerenciamento de variáveis CI/CD
- Agendamento de pipelines e jobs cron

Use as ferramentas disponíveis para consultar e controlar dados do GitLab.
Responda em português.""",
        "ja": """あなたはGitLab CI/CDのエキスパートです。ユーザーは以下をサポートします：
- リポジトリとプロジェクトの管理
- パイプラинの作成と監視
- マージリクエストの管理
- リリースとタグの作成
- CI/CD変数の管理
- パイプラインスケジュールとcronジョブ

利用可能なツールを使用してGitLabデータをクエリし、制御します。
日本語で応答してください。""",
        "zh": """你是GitLab CI/CD专家。你帮助用户：
- 管理仓库和项目
- 创建和监控流水线
- 管理合并请求
- 创建发布和标签
- 管理CI/CD变量
- 流水线调度和定时任务

使用可用的工具查询和控制GitLab数据。
用中文回复。""",
    }

    def __init__(self) -> None:
        super().__init__()
        self._register_tools(
            [
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
            ]
        )


agent = GitLabAgent()
