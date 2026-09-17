"""Pydantic 请求/响应模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    emoji: str = "🤖"
    description: str = ""
    agent_type: str = "react"  # react | pipeline
    system_prompt: str = ""
    tools: list[str] = []
    dataset_ids: list[str] = []
    llm_config: dict = {}
    memory_config: dict = {}
    pipeline: list[dict] = []
    max_iterations: int = 6
    enabled: bool = True


class AgentUpdate(BaseModel):
    name: str | None = None
    emoji: str | None = None
    description: str | None = None
    agent_type: str | None = None
    system_prompt: str | None = None
    tools: list[str] | None = None
    dataset_ids: list[str] | None = None
    llm_config: dict | None = None
    memory_config: dict | None = None
    pipeline: list[dict] | None = None
    max_iterations: int | None = None
    enabled: bool | None = None


class ChatRequest(BaseModel):
    agent_id: str
    message: str = Field(min_length=1)
    conversation_id: str | None = None
    stream: bool = True


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    kind: str = "docs"  # docs | table
