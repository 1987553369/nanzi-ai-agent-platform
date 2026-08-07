import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.api.portal.endpoints.examples import _chatbi_example_user_join
from app.models.chatbi_example import ChatBIExample
from app.models.user import User


pytestmark = pytest.mark.no_infrastructure


def test_chatbi_examples_user_join_casts_numeric_user_id_for_postgresql():
    statement = select(ChatBIExample.id).select_from(ChatBIExample).outerjoin(
        User,
        _chatbi_example_user_join(),
    )

    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "CAST(ai_agent_users.id AS VARCHAR)" in sql
    assert "ai_agent_users.id = ai_chatbi_examples.user_id" not in sql
