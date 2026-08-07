import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestSSOUserList:
    """测试 SSO 用户列表查询功能"""

    def test_get_sso_user_list(self):
        """SSO 用户同步使用安全异步客户端并正确解析用户状态。"""
        from app.services.sso_user import LaplacePortalApiClient

        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "data": [
                {
                    "displayName": "测试用户",
                    "loginName": "TEST.USER",
                    "userEmail": "test@example.com",
                    "userMobile": "13800000000",
                    "departmentName": "研发部",
                    "positionName": "工程师",
                    "userStatus": 0,
                    "userInfo": "test-user-info",
                }
            ]
        }
        client = AsyncMock()
        client.post.return_value = response

        with patch(
            "app.services.sso_user.create_ssrf_safe_async_client"
        ) as client_factory:
            client_factory.return_value.__aenter__.return_value = client
            users = asyncio.run(LaplacePortalApiClient.get_all_users())

        assert users == [
            {
                "code": "test.user",
                "name": "测试用户",
                "email": "test@example.com",
                "status": True,
                "mobile": "13800000000",
                "department": "研发部",
                "position": "工程师",
                "userinfo": "test-user-info",
            }
        ]
        client_factory.assert_called_once()
        assert client_factory.call_args.kwargs["allowed_url"] == (
            "https://yovole.net/api/v1/user/list"
        )
        client.post.assert_awaited_once()
        response.raise_for_status.assert_called_once_with()
