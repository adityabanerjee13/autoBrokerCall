"""The ONLY module in this codebase that constructs a model client.

Every model call in the system goes through `complete()`. If you find yourself
importing AsyncAzureOpenAI anywhere else, put the call here instead.
"""
import logging
from functools import lru_cache
from typing import Any

from openai import AsyncAzureOpenAI

from app.config import settings

log = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """Raised when no Azure AI Foundry deployment is configured or reachable."""


@lru_cache
def client() -> AsyncAzureOpenAI:
    if settings.azure_use_managed_identity:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        token = get_bearer_token_provider(
            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
        )
        return AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            azure_ad_token_provider=token,
            api_version=settings.azure_openai_api_version,
        )
    return AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )


DEPLOYMENT = {
    "agent": settings.azure_deployment_agent,
    "analyzer": settings.azure_deployment_analyzer,
    "composer": settings.azure_deployment_composer,
}


def available() -> bool:
    """Whether a real deployment is configured. Callers fall back when False."""
    return settings.llm_configured


async def complete(role: str, messages: list[dict], **kw) -> Any:
    """One chat completion. `role` is one of agent | analyzer | composer.

    On Azure, `model` is the DEPLOYMENT NAME, not the model name.
    """
    if not available():
        raise LLMUnavailable(
            "AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY are not configured"
        )
    return await client().chat.completions.create(
        model=DEPLOYMENT[role], messages=messages, **kw
    )


async def complete_json(
    role: str, messages: list[dict], schema_name: str, schema: dict, **kw
) -> str:
    """Structured output helper. Returns the raw JSON string content."""
    resp = await complete(
        role,
        messages,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": True},
        },
        **kw,
    )
    return resp.choices[0].message.content or "{}"
