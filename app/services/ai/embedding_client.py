"""Embedding API client (OpenAI-compatible).

Uses system-wide embed_* config for all callers (memory, metadata, examples).
"""
import logging
from typing import List

from app.services.config_service import ConfigService
from app.utils.model_providers import create_model_outbound_client

logger = logging.getLogger(__name__)


class EmbeddingClient:
    @staticmethod
    async def _resolve_credentials(use_global: bool = True) -> tuple[str, str, str]:
        """Resolve Embedding credentials from system config.

        ``use_global`` is retained for call-site compatibility; all paths now
        read ``embed_*`` (with LLM URL/Key fallback). Memory-specific
        ``memory_embedding_*`` keys are no longer consulted.
        """
        _ = use_global  # unused; kept for API compatibility
        base_url = (await ConfigService.get("embed_api_url") or "").strip()
        api_key = (await ConfigService.get("embed_api_key") or "").strip()
        model = (await ConfigService.get("embed_model_name") or "").strip() or "bge-m3"
        if not base_url:
            base_url = (await ConfigService.get("llm_base_url") or "").strip()
        if not api_key:
            api_key = (await ConfigService.get("llm_api_key") or "").strip()
        return base_url.rstrip("/"), api_key, model

    @staticmethod
    async def embed_text(text: str, use_global: bool = True) -> List[float]:
        base_url, api_key, model = await EmbeddingClient._resolve_credentials(use_global)
        provider = None
        try:
            from app.services.ai.model_registry import ModelRegistryError, lookup_registered_model
            from app.utils.model_credentials import decrypt_model_api_key

            registered = await lookup_registered_model(model)
            if registered is not None:
                if getattr(registered, "type", None) != "embedding":
                    raise RuntimeError(f"模型不是 Embedding 类型：{model}")
                model = str(getattr(registered, "model_id", model))
                provider = getattr(registered, "provider", None)
                base_url = (getattr(registered, "api_base_url", None) or base_url).strip()
                api_key = decrypt_model_api_key(getattr(registered, "api_key", None)) or api_key
        except ModelRegistryError:
            raise
        except Exception as exc:
            # Registry lookup is additive for legacy global settings;
            # an unavailable registry must not break those existing settings.
            logger.debug("Embedding model registry lookup unavailable: %s", exc)

        if not base_url or not api_key:
            raise RuntimeError(
                "Embedding API 未配置：请在系统配置中配置全局 Embedding URL 与 Key"
            )

        base = base_url.rstrip("/")
        if base.endswith("/embeddings"):
            url = base
        elif base.endswith("/v1"):
            url = f"{base}/embeddings"
        else:
            url = f"{base}/v1/embeddings"

        payload = {"model": model, "input": text}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        request_url = url
        if str(provider or "").strip().lower() == "azure":
            from app.utils.model_providers import azure_openai_request_config

            chat_url, api_version = azure_openai_request_config(base_url, model)
            request_url = f"{chat_url.rstrip('/')}/embeddings"
            request_url = f"{request_url}?api-version={api_version}"
            headers.pop("Authorization", None)
            headers["api-key"] = api_key

        async with create_model_outbound_client(
            provider=provider,
            request_url=request_url,
            timeout=60.0,
        ) as client:
            resp = await client.post(request_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        items = data.get("data") or []
        if not items:
            raise RuntimeError("Embedding API 返回空 data")
        embedding = items[0].get("embedding")
        if not embedding:
            raise RuntimeError("Embedding API 返回无 embedding 字段")
        return [float(x) for x in embedding]

    @staticmethod
    async def get_dimensions(use_global: bool = True) -> int:
        """Return configured embedding dimensions from system ``embed_dimensions``."""
        _ = use_global  # unused; kept for API compatibility
        dim_str = await ConfigService.get("embed_dimensions")
        if dim_str and str(dim_str).isdigit():
            return int(dim_str)
        return 1024
