"""Integration-scoped outbound clients for explicitly approved private services."""

from typing import Literal

import httpx

from app.core.config import settings
from app.utils.outbound_url_policy import (
    create_private_network_access_policy,
    create_ssrf_safe_async_client,
    outbound_url_origin,
)

IntegrationName = Literal["ragflow", "openclaw", "external_sql"]


def _private_network_config(
    integration: IntegrationName,
) -> tuple[list[str], list[str]]:
    if integration == "ragflow":
        return (
            settings.RAGFLOW_ALLOWED_PRIVATE_HOSTS,
            settings.RAGFLOW_ALLOWED_PRIVATE_CIDRS,
        )
    if integration == "openclaw":
        return (
            settings.OPENCLAW_ALLOWED_PRIVATE_HOSTS,
            settings.OPENCLAW_ALLOWED_PRIVATE_CIDRS,
        )
    if integration == "external_sql":
        return (
            settings.EXTERNAL_SQL_ALLOWED_PRIVATE_HOSTS,
            settings.EXTERNAL_SQL_ALLOWED_PRIVATE_CIDRS,
        )
    raise ValueError(f"不支持的出网集成类型: {integration}")


def _private_network_policy(integration: IntegrationName):
    allowed_hosts, allowed_cidrs = _private_network_config(integration)
    return create_private_network_access_policy(allowed_hosts, allowed_cidrs)


def integration_urls_share_origin(
    integration: IntegrationName,
    first_url: str,
    second_url: str,
) -> bool:
    private_network_policy = _private_network_policy(integration)
    return outbound_url_origin(
        first_url,
        private_network_policy=private_network_policy,
    ) == outbound_url_origin(
        second_url,
        private_network_policy=private_network_policy,
    )


def create_integration_outbound_client(
    integration: IntegrationName,
    *,
    allowed_url: str,
    **kwargs,
) -> httpx.AsyncClient:
    """Create an Origin-bound client with this integration's private approvals."""
    private_network_policy = _private_network_policy(integration)
    return create_ssrf_safe_async_client(
        allowed_url=allowed_url,
        private_network_policy=private_network_policy,
        **kwargs,
    )
