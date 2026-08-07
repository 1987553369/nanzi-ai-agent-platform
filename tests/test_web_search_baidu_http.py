"""百度 HTTP 轻量搜索工具（无 Playwright）。"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai.tools.advanced_auxiliary_tools import web_search_baidu_http

pytestmark = pytest.mark.no_infrastructure


def _baidu_serp_html() -> str:
    return """
    <html>
      <body>
        <div id="content_left">
          <div class="result c-container">
            <h3 class="t">
              <a href="http://example.com/link1">HTTP搜索标题一</a>
            </h3>
            <div class="c-span-last">
              这是第一条 HTTP 搜索结果摘要。
            </div>
          </div>
          <div class="result c-container">
            <h3 class="t">
              <a href="http://example.com/link2">HTTP搜索标题二</a>
            </h3>
            <span class="abstract">
              这是第二条 HTTP 搜索结果摘要。
            </span>
          </div>
        </div>
      </body>
    </html>
    """


@pytest.mark.asyncio
async def test_web_search_baidu_http_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = _baidu_serp_html()
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
        result = await web_search_baidu_http.ainvoke(
            {"query": "南孜平台", "max_results": 2}
        )

    assert "百度 HTTP 搜索结果 (关于: '南孜平台')" in result
    assert "HTTP搜索标题一" in result
    assert "HTTP搜索标题二" in result
    assert "这是第一条 HTTP 搜索结果摘要" in result
    assert "http://example.com/link1" in result
    safe_get.assert_awaited()
    called_url = safe_get.await_args.args[1]
    assert "baidu.com/s" in called_url
    assert "南孜" in called_url or "%E5%8D%97%E5%AD%9C" in called_url


@pytest.mark.asyncio
async def test_web_search_baidu_http_no_results():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body><div>没有结果</div></body></html>"
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
        result = await web_search_baidu_http.ainvoke(
            {"query": "不存在的词", "max_results": 2}
        )

    assert "未能检索到任何相关结果" in result
    assert "web_search_baidu" in result


@pytest.mark.asyncio
async def test_web_search_baidu_http_not_system_implicit():
    from app.services.ai.tools.registry import ToolRegistry

    names = {
        getattr(tool, "name", None) or getattr(tool, "__name__", "")
        for tool in ToolRegistry.get_system_implicit_tools()
    }
    assert "web_search_baidu_http" not in names
    assert "web_search_baidu" not in names
    assert "fetch_static_web_url" not in names
