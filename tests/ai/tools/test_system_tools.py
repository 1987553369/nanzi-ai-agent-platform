import pytest
import httpx
from unittest.mock import patch, AsyncMock
from app.services.ai.tools.system_tools import validate_url, system_http_request

# --- URL Validation Tests ---

def test_validate_url_safe():
    """测试合法的外部 URL"""
    assert validate_url("https://www.google.com") is True

def test_validate_url_internal_ip():
    """测试拦截内网 IP"""
    with pytest.raises(ValueError, match="公网"):
        validate_url("http://192.168.1.1/api")

def test_validate_url_loopback():
    """测试拦截回环地址"""
    with pytest.raises(ValueError, match="本机"):
        validate_url("http://localhost:8000")

def test_validate_url_invalid():
    """测试不合法的 URL"""
    with pytest.raises(Exception):
        validate_url("not-a-url")

# --- System HTTP Request Tests ---

@pytest.mark.asyncio
async def test_system_http_request_success():
    """测试正常的 HTTP 请求"""
    with patch(
        "app.services.ai.tools.system_tools.create_ssrf_safe_async_client"
    ) as client_factory:
        mock_client = AsyncMock()
        client_factory.return_value.__aenter__.return_value = mock_client
        mock_get = mock_client.get
        mock_get.return_value = httpx.Response(200, json={"status": "ok"})
        
        result = await system_http_request.ainvoke({
            "method": "GET",
            "url": "https://api.github.com/zen"
        })
        
        assert "ok" in result
        mock_get.assert_called_once()

@pytest.mark.asyncio
async def test_system_http_request_ssrf_blocked():
    """测试被 SSRF 拦截的情况"""
    result = await system_http_request.ainvoke({
        "method": "GET",
        "url": "http://127.0.0.1/admin"
    })

    assert "Error executing request" in result
    assert "不是公网" in result

@pytest.mark.asyncio
async def test_system_http_request_post():
    """测试 POST 请求"""
    with patch(
        "app.services.ai.tools.system_tools.create_ssrf_safe_async_client"
    ) as client_factory:
        mock_client = AsyncMock()
        client_factory.return_value.__aenter__.return_value = mock_client
        mock_request = mock_client.request
        mock_request.return_value = httpx.Response(201, content="Created")
        
        result = await system_http_request.ainvoke({
            "method": "POST",
            "url": "https://api.test.com/v1",
            "body": {"key": "val"}
        })
        
        assert "Created" in result
        args, kwargs = mock_request.call_args
        assert kwargs["json"] == {"key": "val"}
