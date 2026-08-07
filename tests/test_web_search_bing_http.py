"""Bing HTTP 轻量搜索工具（无 Playwright）。"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai.tools.advanced_auxiliary_tools import web_search_bing_http

pytestmark = pytest.mark.no_infrastructure


def _bing_serp_html() -> str:
    return """
    <html>
      <body>
        <ol id="b_results">
          <li class="b_algo">
            <h2><a href="https://example.com/a">Bing Result One</a></h2>
            <div class="b_caption"><p>First Bing snippet about NanZi.</p></div>
          </li>
          <li class="b_algo">
            <h2><a href="https://example.com/b">Bing Result Two</a></h2>
            <p class="b_algoSlug">Second Bing snippet.</p>
          </li>
        </ol>
      </body>
    </html>
    """


@pytest.mark.asyncio
async def test_web_search_bing_http_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = _bing_serp_html()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.services.ai.tools.advanced_auxiliary_tools.create_ssrf_safe_async_client",
        return_value=mock_client,
    ), patch(
        "app.services.ai.tools.advanced_auxiliary_tools.get_with_ssrf_safe_redirects",
        new=AsyncMock(return_value=mock_response),
    ) as safe_get:
        result = await web_search_bing_http.ainvoke(
            {"query": "NanZi platform", "max_results": 2}
        )

    assert "Bing HTTP 搜索结果 (关于: 'NanZi platform')" in result
    assert "Bing Result One" in result
    assert "Bing Result Two" in result
    assert "First Bing snippet about NanZi" in result
    assert "https://example.com/a" in result
    called_url = safe_get.await_args.args[1]
    assert "bing.com/search" in called_url


@pytest.mark.asyncio
async def test_web_search_bing_http_no_results():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body><div>no results</div></body></html>"
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.services.ai.tools.advanced_auxiliary_tools.create_ssrf_safe_async_client",
        return_value=mock_client,
    ), patch(
        "app.services.ai.tools.advanced_auxiliary_tools.get_with_ssrf_safe_redirects",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await web_search_bing_http.ainvoke(
            {"query": "zzzz-not-found", "max_results": 2}
        )

    assert "未能检索到任何相关结果" in result
    assert "web_search_baidu_http" in result


@pytest.mark.asyncio
async def test_web_search_bing_http_not_system_implicit():
    from app.services.ai.tools.registry import ToolRegistry

    names = {
        getattr(tool, "name", None) or getattr(tool, "__name__", "")
        for tool in ToolRegistry.get_system_implicit_tools()
    }
    assert "web_search_bing_http" not in names
