from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "brokeragent"

    # Azure AI Foundry
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_use_managed_identity: bool = False
    azure_deployment_agent: str = "gpt-4o-broker"
    azure_deployment_analyzer: str = "gpt-4o-analyzer"
    azure_deployment_composer: str = "gpt-4o-mini-composer"

    # Outbound providers
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    email_api_key: str = ""

    # Dograh - the agent orchestrator. https://docs.dograh.com
    #
    # Dograh owns the call: the VoBiz carrier leg, Azure Speech in both
    # directions, and the conversation graph that decides what to say. All of
    # that is configured inside Dograh, not here - this app holds only what it
    # needs to hand a call over and get the result back.
    #
    # dograh_api_key           Settings -> API Keys in the Dograh dashboard
    # dograh_workflow_uuid     the agent's UUID, not an API Trigger node's
    # dograh_shared_secret     our side: proves a tool call or webhook came
    #                          from our Dograh workflow and not from the
    #                          internet at large
    dograh_api_base: str = "https://app.dograh.com"
    dograh_api_key: str = ""
    dograh_workflow_uuid: str = ""
    dograh_shared_secret: str = ""

    # Which of Dograh's telephony configurations to dial with. Leave unset to
    # let Dograh pick the first one that is ready for outbound.
    dograh_telephony_configuration_id: int | None = None
    dograh_from_phone_number_id: int | None = None

    # Where Dograh can reach this app, for HTTP API tools and the completion
    # webhook. A public HTTPS origin, no trailing slash. Only needed when
    # Dograh runs somewhere that cannot see localhost.
    public_base_url: str = ""

    # Where the lead's side of a call happens.
    #   dograh - a real call, orchestrated by Dograh: VoBiz carries it and
    #            Azure Speech is its voice. This is the product.
    #   mock   - a scripted lead replayed from seed/scripts. Needs no Dograh
    #            account at all, and is what the demo runs on.
    # There is no third value.
    call_transport: str = "mock"

    # Demo switches
    mock_outbound: bool = True

    # Frontend origins allowed by CORS
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @property
    def transport(self) -> str:
        """The resolved call transport. One knob, two values.

        `dograh` is the only value that places a real call, and it degrades to
        the script unless there is an API key and a workflow to run: a
        half-configured .env should replay a scripted lead, not fail at the
        orchestrator.
        """
        wanted = (self.call_transport or "").strip().lower()
        if wanted == "dograh" and self.dograh_configured:
            return "dograh"
        return "mock"

    @property
    def dograh_configured(self) -> bool:
        """True when a call could actually be handed to Dograh.

        The shared secret is part of the answer, not an optional extra: without
        it the tool endpoints this app exposes have nothing to authenticate,
        and they are the agent's only route to the database.
        """
        return all(
            v and "<" not in v
            for v in (
                self.dograh_api_base,
                self.dograh_api_key,
                self.dograh_workflow_uuid,
                self.dograh_shared_secret,
            )
        )

    @property
    def dograh_trigger_url(self) -> str:
        """Where an outbound call is handed over.

        The agent's own UUID goes in this path. An API Trigger node's UUID is
        a different id and a 404 here.
        """
        return (
            f"{self.dograh_api_base.rstrip('/')}"
            f"/api/v1/public/agent/workflow/{self.dograh_workflow_uuid}"
        )

    @property
    def llm_configured(self) -> bool:
        """True when a real Azure AI Foundry endpoint is reachable-looking."""
        if not self.azure_openai_endpoint or "<" in self.azure_openai_endpoint:
            return False
        if self.azure_use_managed_identity:
            return True
        return bool(self.azure_openai_api_key) and "<" not in self.azure_openai_api_key


settings = Settings()

POLICY_PATH = BACKEND_ROOT / "config" / "policy.yaml"


@lru_cache
def policy() -> dict[str, Any]:
    with POLICY_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)
