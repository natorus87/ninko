"""GitHub module schemas."""

from typing import Optional, List
from pydantic import BaseModel


class GitHubConnection(BaseModel):
    name: str
    token: str


class GitHubRepository(BaseModel):
    id: int
    name: str
    full_name: str
    private: bool
    html_url: str
    description: Optional[str] = None
    default_branch: str = "main"
    language: Optional[str] = None


class GitHubWorkflow(BaseModel):
    id: int
    name: str
    state: str
    path: str


class GitHubWorkflowRun(BaseModel):
    id: int
    name: str
    head_branch: str
    head_sha: str
    status: str
    conclusion: Optional[str] = None
    html_url: str
    created_at: str
    updated_at: str


class GitHubJob(BaseModel):
    id: int
    name: str
    status: str
    conclusion: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class GitHubPullRequest(BaseModel):
    id: int
    number: int
    title: str
    state: str
    html_url: str
    user: dict
    base: dict
    head: dict
    created_at: str


class GitHubIssue(BaseModel):
    id: int
    number: int
    title: str
    state: str
    html_url: str
    user: dict
    labels: List[dict]
    created_at: str


class GitHubCommit(BaseModel):
    sha: str
    message: str
    author: dict
    date: str


class GitHubRelease(BaseModel):
    id: int
    tag_name: str
    name: str
    body: str
    html_url: str
    published_at: str


class GitHubTag(BaseModel):
    name: str
    commit: dict


class GitHubBranch(BaseModel):
    name: str
    commit: dict
    protected: bool


class GitHubSecret(BaseModel):
    name: str
    visibility: str


class GitHubVariable(BaseModel):
    name: str
    value: str
