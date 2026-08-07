# 配置键清单

## 环境变量配置

| 配置键 | 类型 | 默认值 | 源码位置 |
|---|---|---|---|
| `API_SERVICE_ENV` | `str` | `'dev'` | `app/core/config.py:8` |
| `API_SERVICE_PORT` | `int` | `8001` | `app/core/config.py:9` |
| `LOG_LEVEL` | `str` | `'INFO'` | `app/core/config.py:10` |
| `ALLOWED_ORIGINS` | `List[str]` | `['*']` | `app/core/config.py:11` |
| `APP_PUBLIC_URL` | `Optional[str]` | `None` | `app/core/config.py:12` |
| `DATABASE_TYPE` | `str` | `'mysql'` | `app/core/config.py:15` |
| `MYSQL_HOST` | `Optional[str]` | `None` | `app/core/config.py:18` |
| `MYSQL_PORT` | `int` | `3306` | `app/core/config.py:19` |
| `MYSQL_DB` | `Optional[str]` | `None` | `app/core/config.py:20` |
| `MYSQL_USER` | `Optional[str]` | `None` | `app/core/config.py:21` |
| `MYSQL_PASSWORD` | `Optional[str]` | `None` | `app/core/config.py:22` |
| `MYSQL_POOL_SIZE` | `int` | `20` | `app/core/config.py:23` |
| `MYSQL_MAX_OVERFLOW` | `int` | `50` | `app/core/config.py:24` |
| `MYSQL_POOL_RECYCLE` | `int` | `3600` | `app/core/config.py:25` |
| `POSTGRES_HOST` | `str` | `'localhost'` | `app/core/config.py:28` |
| `POSTGRES_PORT` | `int` | `5432` | `app/core/config.py:29` |
| `POSTGRES_DB` | `Optional[str]` | `None` | `app/core/config.py:30` |
| `POSTGRES_USER` | `Optional[str]` | `None` | `app/core/config.py:31` |
| `POSTGRES_PASSWORD` | `Optional[str]` | `None` | `app/core/config.py:32` |
| `REDIS_HOST` | `str` | `required` | `app/core/config.py:35` |
| `REDIS_PORT` | `int` | `6379` | `app/core/config.py:36` |
| `REDIS_DB` | `int` | `0` | `app/core/config.py:37` |
| `REDIS_PASSWORD` | `Optional[str]` | `None` | `app/core/config.py:38` |
| `REDIS_ENABLE` | `bool` | `True` | `app/core/config.py:39` |
| `ENCRYPTION_KEY` | `str` | `required` | `app/core/config.py:43` |
| `LLM_BASE_URL` | `Optional[str]` | `None` | `app/core/config.py:46` |
| `LLM_API_KEY` | `Optional[str]` | `None` | `app/core/config.py:47` |
| `LLM_MODEL_NAME` | `Optional[str]` | `None` | `app/core/config.py:48` |
| `LLM_TEMPERATURE` | `Optional[float]` | `None` | `app/core/config.py:49` |
| `EXTERNAL_SQL_API_URL` | `Optional[str]` | `None` | `app/core/config.py:59` |
| `EXTERNAL_SQL_API_KEY` | `Optional[str]` | `None` | `app/core/config.py:60` |
| `EXTERNAL_SQL_ALLOWED_PRIVATE_HOSTS` | `List[str]` | `[]` | `app/core/config.py:61` |
| `EXTERNAL_SQL_ALLOWED_PRIVATE_CIDRS` | `List[str]` | `[]` | `app/core/config.py:62` |
| `METADATA_PROVIDER` | `str` | `'local'` | `app/core/config.py:65` |
| `RAGFLOW_API_URL` | `Optional[str]` | `None` | `app/core/config.py:66` |
| `RAGFLOW_API_KEY` | `Optional[str]` | `None` | `app/core/config.py:67` |
| `RAGFLOW_ALLOWED_PRIVATE_HOSTS` | `List[str]` | `[]` | `app/core/config.py:68` |
| `RAGFLOW_ALLOWED_PRIVATE_CIDRS` | `List[str]` | `[]` | `app/core/config.py:69` |
| `OPENCLAW_ALLOWED_PRIVATE_HOSTS` | `List[str]` | `[]` | `app/core/config.py:70` |
| `OPENCLAW_ALLOWED_PRIVATE_CIDRS` | `List[str]` | `[]` | `app/core/config.py:71` |
| `MEMORY_BASE_HALF_LIFE` | `float` | `7.0` | `app/core/config.py:74` |
| `MEMORY_CONSOLIDATION_THRESHOLD` | `float` | `0.82` | `app/core/config.py:75` |
| `SSO_API_URL` | `str` | `'https://yovole.net/api/v1/user/check/login'` | `app/core/config.py:78` |
| `SSO_ACCESS_TOKEN` | `str` | `'CHANGE_ME_SSO_ACCESS_TOKEN'` | `app/core/config.py:80` |
| `SSO_REQUEST_SYSTEM` | `str` | `'NANZI_AI_AGENT_PLATFORM'` | `app/core/config.py:81` |
| `SSO_REQUEST_BUSINESS` | `str` | `'USER-LOGIN'` | `app/core/config.py:82` |
| `SSO_TIMEOUT` | `int` | `30` | `app/core/config.py:83` |

## 数据库存储的系统配置

| 配置键 | 引用位置 |
|---|---|
| `agent_context_compaction_enabled` | `app/services/ai/agent_service.py` |
| `agent_context_compaction_max_chars` | `app/services/ai/agent_service.py` |
| `agent_empty_response_fallback_enabled` | `app/services/ai/agent_service.py` |
| `agent_max_context_messages` | `app/services/ai/agent_service.py` |
| `agent_max_iterations` | `app/services/ai/runners/assistant_agent_runner.py, app/services/ai/runners/data_agent_runner.py, app/services/ai/runners/knowledge_agent_runner.py` |
| `agent_prompt_cache_boundary_enabled` | `app/services/ai/prompt_assembler.py` |
| `agent_prompt_cache_reorder_enabled` | `app/services/ai/prompt_assembler.py` |
| `agent_session_followup_wait_mode` | `app/services/ai/runtime/session_run_lane.py` |
| `agent_session_followup_wait_seconds` | `app/services/ai/runtime/session_run_lane.py` |
| `agent_session_queue_followup_wait_seconds` | `app/services/ai/runtime/session_run_lane.py` |
| `agent_session_queue_mode` | `app/services/ai/runtime/session_run_lane.py` |
| `agent_session_run_lock_enabled` | `app/services/ai/runtime/session_run_lane.py` |
| `agent_session_run_lock_ttl_seconds` | `app/services/ai/runtime/session_run_lane.py` |
| `agent_session_run_lock_wait_seconds` | `app/services/ai/runtime/session_run_lane.py` |
| `agent_tool_loop_detection_enabled` | `app/services/ai/runners/assistant_agent_runner.py` |
| `agent_tool_loop_fuse_threshold` | `app/services/ai/runners/assistant_agent_runner.py` |
| `agent_tool_loop_global_limit` | `app/services/ai/runners/assistant_agent_runner.py` |
| `agent_tool_loop_ping_pong_threshold` | `app/services/ai/runners/assistant_agent_runner.py` |
| `agent_tool_preflight_mode` | `app/services/ai/runners/assistant_agent_runner.py` |
| `agentscope_workspace_root` | `app/services/ai/runtime/agentscope/workspace.py` |
| `audit_log_retention_days` | `app/api/portal/endpoints/system.py, app/services/ai/scheduler_service.py` |
| `chatbi_sample_knowledge_base` | `app/services/chatbi_example_service.py` |
| `chatbi_sample_similarity_threshold` | `app/services/chatbi_example_service.py` |
| `chatbi_sample_top_k` | `app/services/chatbi_example_service.py` |
| `chatbi_sample_vector_similarity_weight` | `app/services/chatbi_example_service.py` |
| `data_api_timeout_seconds` | `app/services/ai/tools/data_api.py` |
| `embed_api_key` | `app/api/portal/endpoints/system.py, app/services/ai/embedding_client.py` |
| `embed_api_url` | `app/api/portal/endpoints/system.py, app/api/v1/endpoints/schema.py, app/services/ai/embedding_client.py` |
| `embed_dimensions` | `app/api/v1/endpoints/schema.py, app/services/ai/embedding_client.py` |
| `embed_model_name` | `app/api/portal/endpoints/system.py, app/api/v1/endpoints/schema.py, app/services/ai/embedding_client.py` |
| `embedchat_watermark_enabled` | `app/api/portal/endpoints/auth.py` |
| `embedchat_watermark_style` | `app/api/portal/endpoints/auth.py` |
| `embedchat_watermark_text` | `app/api/portal/endpoints/auth.py` |
| `external_sql_api_key` | `app/services/ai/tools/data_api.py` |
| `external_sql_api_url` | `app/services/ai/tools/data_api.py` |
| `external_sql_data_source` | `app/services/ai/dimension_enrichment_service.py, app/services/ai/tools/data_api.py, app/services/chatbi_dataset_schema_service.py, app/services/metadata_service.py` |
| `knowledge_base_enabled` | `app/services/ai/knowledge_utils.py` |
| `knowledge_ragflow_api_key` | `app/api/portal/endpoints/ragflow.py` |
| `knowledge_ragflow_api_url` | `app/api/portal/endpoints/ragflow.py` |
| `knowledge_ragflow_dataset_ids` | `app/services/ai/knowledge_utils.py, app/services/permission_service.py` |
| `knowledge_ragflow_metadata_top_k` | `app/services/ai/knowledge_utils.py, app/services/ai/tools/knowledge_tool.py` |
| `knowledge_ragflow_similarity_threshold` | `app/services/ai/knowledge_utils.py, app/services/ai/runners/knowledge_agent_runner.py, app/services/ai/tools/knowledge_tool.py` |
| `knowledge_ragflow_vector_weight` | `app/services/ai/knowledge_utils.py, app/services/ai/tools/knowledge_tool.py` |
| `llm_api_key` | `app/api/portal/endpoints/system.py, app/services/ai/embedding_client.py` |
| `llm_base_url` | `app/api/portal/endpoints/system.py, app/services/ai/embedding_client.py` |
| `llm_model_name` | `app/services/ai/agent_manager.py, app/services/ai/agent_service.py, app/services/ai/context_manager.py` |
| `metadata_provider` | `app/api/portal/endpoints/ragflow.py, app/api/v1/endpoints/schema.py, app/services/ai/local_vector_rebuild.py, app/services/chatbi_dataset_schema_service.py, app/services/chatbi_example_service.py, app/services/metadata_service.py` |
| `openclaw_api_key` | `app/services/ai/openclaw_client.py` |
| `openclaw_api_url` | `app/services/ai/openclaw_client.py` |
| `ragflow_api_key` | `app/services/ai/tools/data_api.py` |
| `ragflow_api_url` | `app/api/v1/endpoints/schema.py, app/services/ai/tools/data_api.py` |
| `ragflow_metadata_top_k` | `app/services/chatbi_dataset_schema_service.py` |
| `ragflow_similarity_threshold` | `app/api/v1/endpoints/schema.py, app/services/ai/runners/data_agent_runner.py, app/services/chatbi_dataset_schema_service.py` |
| `ragflow_vector_weight` | `app/api/v1/endpoints/schema.py, app/services/chatbi_dataset_schema_service.py` |
| `skill_auto_full_load_enabled` | `app/services/ai/agent_service.py` |
| `skill_auto_full_load_max_bytes` | `app/services/ai/agent_service.py` |
| `skill_auto_full_load_max_count` | `app/services/ai/agent_service.py` |
| `skill_auto_full_load_min_score` | `app/services/ai/agent_service.py` |
| `skill_auto_scan_enabled` | `app/services/ai/agent_service.py` |
| `skill_auto_scan_max_results` | `app/services/ai/agent_service.py` |
| `skill_auto_scan_min_score` | `app/services/ai/agent_service.py` |
| `sql_execution_mode` | `app/api/v1/endpoints/chatbi.py, app/main.py, app/services/ai/tools/data_api.py` |
| `sub_agent_delegation_result_max_chars` | `app/services/ai/tools/agent_delegate_tool.py` |
| `sub_agent_delegation_timeout_seconds` | `app/services/ai/tools/agent_delegate_tool.py` |
| `yovole_sso_enabled` | `app/api/portal/endpoints/auth.py, app/api/portal/endpoints/management.py` |
