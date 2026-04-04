"""GitLab module schemas."""

from typing import Optional, List
from pydantic import BaseModel, Field


class GitLabConnection(BaseModel):
    name: str
    url: str
    token: str


class GitLabProject(BaseModel):
    id: int
    name: str
    path: str
    web_url: str
    description: Optional[str] = None
    default_branch: str = "main"
    visibility: str = "private"


class GitLabPipeline(BaseModel):
    id: int
    status: str
    ref: str
    sha: str
    web_url: str
    created_at: str
    updated_at: str


class GitLabJob(BaseModel):
    id: int
    name: str
    status: str
    stage: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration: Optional[float] = None


class GitLabMergeRequest(BaseModel):
    id: int
    iid: int
    title: str
    state: str
    source_branch: str
    target_branch: str
    web_url: str
    author: dict


class GitLabBranch(BaseModel):
    name: str
    protected: bool
    commit: dict


class GitLabCommit(BaseModel):
    id: str
    short_id: str
    title: str
    author_name: str
    created_at: str


class GitLabRelease(BaseModel):
    tag_name: str
    name: str
    description: str
    released_at: str


class GitLabTag(BaseModel):
    name: str
    message: Optional[str] = None
    commit: dict


class GitLabVariable(BaseModel):
    key: str
    value: str
    variable_type: str = "env_var"


class GitLabArtifact(BaseModel):
    id: int
    filename: str
    size: int
    created_at: str
