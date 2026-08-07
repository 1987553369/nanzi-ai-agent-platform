# NanZi 开源智能体平台部署安装指南 (HOW TO INSTALL)

本指南旨在指导开发和运维人员在本地开发环境或生产环境下完成 **NanZi 开源智能体平台 (NanZi AI Agent Platform)** 的安装部署、数据库表结构初始化以及常见问题的快速排查。

---

## 1. 概要 (Overview)

NanZi 开源智能体平台是企业级的多智能体编排与数据智能洞察（ChatBI）系统。为了适应不同用户的环境，平台主要提供两套部署安装方案：
*   **Docker 容器化部署（生产首选，支持离线）**：通过位置参数指定版本号构建 Docker 归档包，可在隔离容器环境下运行并一键部署。
*   **本地源码开发调试部署（开发首选）**：使用 Python 虚拟环境与 Node.js 宿主机环境，支持前后端热重载实时开发联调。

无论采用何种部署方案，服务拉起前均需要完成平台主库结构与初始管理员账号的初始化。

> **重要：平台主库必须二选一。**
>
> 请根据实际环境选择 **MySQL** 或 **PostgreSQL** 其中一种：
> - 选择 MySQL：配置 `DATABASE_TYPE=mysql`（不配置时默认使用 MySQL），执行 `db-prod/` 初始化脚本。
> - 选择 PostgreSQL：配置 `DATABASE_TYPE=postgresql`，执行 `db-prod-pg/` 初始化脚本。
>
> 同一个平台运行环境不要同时初始化两套主库，也不要交叉执行两套迁移脚本。两套数据库都可以作为外部数据源被平台连接，但平台自身的主库运行时只使用其中一种。

---

## 2. 前置环境 (Prerequisites)

在开始部署平台之前，请确保当前环境满足以下各项依赖条件：

### 💻 基础工具依赖
*   **Docker**（建议 v20.10+） 与 **Docker Compose**（建议 v2.0.0+）
*   **Python**（固定使用 v3.11，用于本地源码调试和安全 SQL 迁移工具。如果直接使用已打好的 Docker 镜像包部署，则无需在宿主机安装）
*   **Node.js**（建议 v18+ & npm，仅用于本地开发联调或宿主机前端预构建。如果不自行构建镜像且不进行本地源码调试，则无需安装）

### 🔌 数据库与外部依赖服务
*   **平台主库（二选一）**：
    *   **MySQL**（建议 v8.0+）：必须支持 `utf8mb4` 字符集，用以存放平台系统级配置、角色权限、审计日志及智能体元数据。
    *   **PostgreSQL**（建议 v14+）：作为 MySQL 的替代主库；初始化脚本使用 PostgreSQL 原生方言和带账本的版本迁移。
*   **Redis**：**必须使用支持向量检索的 Redis Stack 版本**（例如 `redis/redis-stack-server:latest`），用以支持平台内部高并发缓存、长期记忆（LTM）向量检索、向量搜索诊断以及分布式异步调度队列（APScheduler）。
*   **RAGFlow 生态（若使用知识库和 ChatBI，则为必选）**：如需接入非结构化 SOP 知识库或使用 ChatBI 数据洞察功能，必须保证 RAGFlow 服务就绪并提供相应的 API URL 与 API Key。更多信息请参考 [RAGFlow 官网](https://ragflow.io/)。

---

## 3. 部署流程 (Deployment Flow)

### 3.1 主库选项 A：MySQL（二选一）

仅当平台主库选择 MySQL 时执行本节。若选择 PostgreSQL，请跳过本节，直接执行 [3.2 主库选项 B：PostgreSQL](#32-主库选项-bpostgresql二选一)。

平台采用带账本的版本迁移管理（数据库脚本位于 `db-prod/`）。无参数执行导入脚本时，
会自然排序全部 `V*.sql`，在单一数据库锁内校验 Checksum 并执行尚未成功的版本。

> **目标库不存在时会自动创建。**  
> 导入器连接 MySQL 后，若你输入的目标库名尚不存在，会自动执行  
> `CREATE DATABASE IF NOT EXISTS \`...\` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci`，  
> 无需事先手工建库。脚本不会忽略 DDL 错误；任何 SQL 错误都会停止迁移并记录失败状态。

1.  **准备依赖**：
    ```bash
    python3.11 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```
    MySQL 建议使用 **v8.0+**，字符集以 `utf8mb4` 为准。

2.  **执行结构自动初始化**：

    *   **安全迁移入口（推荐）**
        ```bash
        # 推荐：在项目根目录执行
        chmod +x db-prod/apply-sql.sh
        ./db-prod/apply-sql.sh

        # 也可进入目录后执行
        cd db-prod
        ./apply-sql.sh
        ```
        脚本会依次询问 Host、Port、User、Password 和目标数据库，并要求输入 `YES` 确认。  
        无参数时会执行 `db-prod/V*.sql` 全部版本文件。

    *   **历史兼容入口**
        `apply-sql-native.sh` 已停用原生多进程导入，当前会委托给同一个 Python 安全执行器，
        以保证数据库全局锁和账本更新覆盖整个批次：
        ```bash
        chmod +x db-prod/apply-sql-native.sh
        ./db-prod/apply-sql-native.sh
        ```
        *注：该兼容入口同样要求 Python 3.11 及 `aiomysql`。*

3.  **交互导入示例**（首次部署，目标库可不预先创建）：

    以下示例将数据导入到本地库 `test222`（若不存在会自动创建）：

    ```text
    $ cd db-prod
    $ ./apply-sql.sh
    MySQL host [localhost]:                 # 回车使用默认 localhost
    MySQL port [3306]:                      # 回车使用默认 3306
    MySQL user: root
    MySQL password: ******
    Target database: test222                # 不存在则自动创建（utf8mb4）
    ---------------------------------------------------
    请确认本次 SQL 执行目标：
      Host     : localhost
      Port     : 3306
      User     : root
      Database : test222
      Password : ******
      SQL files: db-prod/V*.sql
    确认无误请输入 YES 继续执行：yes
    No arguments provided. Running all SQL files from db-prod/...
    ---------------------------------------------------
    🚀 Applying db-prod/V0-init_yunshu_ai_agent_metadata.sql...
    🔌 Connecting to MySQL server to ensure database 'test222' exists...
    🔌 Connecting to database 'test222'...
    ✅ SQL applied successfully.
    ---------------------------------------------------
    🚀 Applying db-prod/V1-create_system_configs.sql...
    🔌 Connecting to MySQL server to ensure database 'test222' exists...
    ...（后续 V2、V3 … 直至最新版本依次执行）
    ✅ SQL applied successfully.
    ```

    *说明：*
    *   生产环境请将 `Target database` 换成正式库名（如 `nanzi_ai_agent_platform`），并与 `.env` 中的 `MYSQL_DB` / `MYSQL_DATABASE` 保持一致。
    *   已成功版本由 `nanzi_schema_migrations` 账本和 Checksum 判断并跳过，不能通过忽略“对象已存在”错误实现重跑。
    *   可选：仍可事先手工建库（字符集须为 `utf8mb4`），例如：
        ```sql
        CREATE DATABASE IF NOT EXISTS `nanzi_ai_agent_platform` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
        ```

4.  **创建随机管理员凭据（可选）**：
    首次全量初始化完成后，脚本会询问是否创建管理员。若当时跳过，可稍后运行：
    ```bash
    ./db-prod/create-admin-user.sh
    ./db-prod/create-admin-key.sh admin
    ```
    仓库不提供固定默认 API Key，明文凭据只显示一次。

5.  **旧 MySQL 环境首次启用账本**：
    已有业务表但没有迁移账本时，脚本会拒绝从 V0 重放。先备份并由 DBA 核对真实完成版本，
    再执行：
    ```bash
    ./db-prod/apply-sql.sh --baseline-through <当前版本>
    ```
    `failed` / `in_progress` 状态不会自动重试，必须人工核对实际 Schema 后处置。

6.  **升级旧环境的 MCP 凭据**：
    V117 会禁用仍保存明文 Header 的 MCP 服务。结构迁移后、启动新应用前，必须按
    [MCP 历史凭据加密迁移手册](docs/MCP_CREDENTIAL_MIGRATION_CN.md)执行 dry-run、加密迁移和
    人工轮换队列验收。

详细的库表结构说明，请参考：[db-prod/README.md](db-prod/README.md)。

---

### 3.2 主库选项 B：PostgreSQL（二选一）

仅当平台主库选择 PostgreSQL 时执行本节。若选择 MySQL，请跳过本节。不要同时执行 `db-prod/` 和 `db-prod-pg/` 两套主库初始化脚本。

平台同时提供独立的 PostgreSQL 初始化入口，脚本位于 `db-prod-pg/`，不会修改现有
`db-prod/` MySQL 迁移链。新环境会按版本号自动执行 `V0-baseline.sql`、`V1-...sql`
等全部版本文件。重复运行时只跳过账本中 Checksum 一致的成功版本。

> **目标库不存在时会自动创建。**  
> 导入器连接 PostgreSQL 后，若你输入的目标库名尚不存在，会自动执行 `CREATE DATABASE ... WITH ENCODING 'UTF8'`，无需事先手工建库。  
> 但仍须**显式输入目标库名称**；禁止使用 `postgres`、`template0`、`template1` 作为应用库。

1.  **准备依赖**：
    ```bash
    python3.11 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```
    PostgreSQL 目标实例建议使用 **v14+**。

2.  **执行 PostgreSQL 初始化（导入结构与种子数据）**：
    ```bash
    # 推荐：在项目根目录执行
    chmod +x db-prod-pg/apply-sql.sh
    ./db-prod-pg/apply-sql.sh

    # 也可进入目录后执行（兼容 sh）
    cd db-prod-pg
    sh apply-sql.sh
    ```
    无参数时，脚本会按版本号自然排序，在一个 advisory lock 内执行当前目录全部 `V*.sql`。
    脚本会依次询问 Host、Port、User、Password 和目标数据库，并要求输入 `YES` 确认。  
    全部 SQL 成功后，会询问是否顺带创建默认管理员 `admin` 并生成 API Key。

3.  **交互导入示例**（首次部署，目标库可不预先创建）：

    以下示例将数据导入到本地库 `test111`（若不存在会自动创建），并完成管理员初始化：

    ```text
    $ cd db-prod-pg
    $ sh apply-sql.sh
    PostgreSQL host [localhost]:            # 回车使用默认 localhost
    PostgreSQL port [5432]:                 # 回车使用默认 5432
    PostgreSQL user: postgres
    PostgreSQL password: ******
    Target database: test111                # 不存在则自动创建；勿填 postgres/template0/template1
    ---------------------------------------------------
    请确认本次 SQL 执行目标：
      Host     : localhost
      Port     : 5432
      User     : postgres
      Database : test111
      SQL files:
        - .../db-prod-pg/V0-baseline.sql
        - .../db-prod-pg/V1-align_system_config_seeds.sql
        - .../db-prod-pg/V2-update_memory_embedding_default_config.sql
        - .../db-prod-pg/V3-add_mcp_scope_and_user_id.sql
        - .../db-prod-pg/V4-add_category_to_chatbi_examples.sql
        - .../db-prod-pg/V5-register_example_search_tool.sql
        - .../db-prod-pg/V6-enforce_mcp_server_name_uniqueness.sql
        - .../db-prod-pg/V7-add_mcp_tool_availability.sql
        - .../db-prod-pg/V8-enforce_ai_model_id_uniqueness.sql
        - .../db-prod-pg/V15-add_ai_execution_capabilities_compat.sql
      Password : ******
    确认无误请输入 YES 继续执行：yes
    ---------------------------------------------------
    🚀 Applying .../V0-baseline.sql ...
    ✅ SQL applied successfully.
    ...（已登记版本校验后跳过，新版本依次执行）
    ---------------------------------------------------
    ✅ 所有 PostgreSQL 版本 SQL 文件执行成功。
    ---------------------------------------------------
    是否需要顺带创建默认管理员 admin 并生成新的 API Key？ (推荐首次部署时创建) [Y/N]: y
    ✅ 管理员账号创建成功！
    🔑 管理员 API Key（请立即保存）
       用户名: admin
       API Key: <仅显示一次，请立即保存>
    ```

    *说明：*
    *   生产环境请将 `Target database` 换成正式库名（如 `nanzi_ai_agent_platform`），并与下文 `.env` 中的 `POSTGRES_DB` 保持一致。
    *   若只需升级单个版本，可显式传文件，例如：  
        `./db-prod-pg/apply-sql.sh db-prod-pg/V15-add_ai_execution_capabilities_compat.sql`

    *   已有业务表但没有迁移账本时，先备份并核对真实完成版本，再执行：
        `./db-prod-pg/apply-sql.sh --baseline-through <当前版本>`
    *   历史迁移 Checksum 不一致或状态为 `failed` / `in_progress` 时，禁止自动重试，必须人工核对。
    *   V16 会禁用仍保存明文 Header 的 MCP 服务。结构迁移后、启动新应用前，必须按
        [MCP 历史凭据加密迁移手册](docs/MCP_CREDENTIAL_MIGRATION_CN.md)完成加密迁移和轮换队列验收。

4.  **管理员初始化与凭证维护（若第 2 步已选 Y 可跳过）**：
    PostgreSQL 基线不写入固定管理员 API Key。初始化时选择 `Y` 会使用当前
    `ENCRYPTION_KEY` 生成新的管理员凭证；如果初始化时跳过，可在配置好运行环境后执行：
    ```bash
    ./db-prod-pg/create-admin-user.sh
    ./db-prod-pg/create-admin-key.sh
    ./db-prod-pg/reset-admin-password.sh
    ```
    API Key 只在终端显示一次，请立即保存。三个脚本分别用于创建管理员、重新生成 API Key
    和重置管理员密码。

5.  **配置平台运行时**：
    在项目根目录 `.env` 中选择 PostgreSQL 主库（`POSTGRES_DB` 须与导入时的目标库名一致）：
    ```dotenv
    DATABASE_TYPE=postgresql
    POSTGRES_HOST=localhost
    POSTGRES_PORT=5432
    POSTGRES_DB=test111
    POSTGRES_USER=postgres
    POSTGRES_PASSWORD=<password>
    ```
    不配置 `DATABASE_TYPE` 时默认仍使用 MySQL。应用 ORM 和 APScheduler 会根据该值选择
    PostgreSQL 或 MySQL 连接。

详细的 PostgreSQL 初始化、版本迁移和管理员脚本说明，请参考
[db-prod-pg/README.md](db-prod-pg/README.md)。

---

完成上面 MySQL 或 PostgreSQL 两个主库选项中的任意一个后，再根据部署方式选择以下方案。

### 3.3 方案 A：Docker 容器化部署 (推荐)
通过 Docker 容器化可以避免环境依赖缺失造成的各种意外错误。

1.  **获取离线镜像包（提供以下两种途径）**：

    *   **途径一：直接下载官方预编译镜像包（推荐，最便捷）**
        直接前往 [GitHub Releases](https://github.com/RandyChen1985/nanzi-ai-agent-platform/releases) 页面，下载对应版本以及适合您服务器 CPU 架构（如 `linux-amd64` / `linux-arm64`）的离线 Docker 镜像归档 tar 包。
        
    *   **途径二：本地自行编译并导出镜像包（适合二次开发与定制）**
        执行入口构建脚本时，**必须显式在第一位传入版本号参数**（如 `1.0.0`）：
        ```bash
        cd docker
        
        # 构建 x86_64 架构 Linux 镜像
        ./build_linux_x86.sh 1.0.0
        
        # 构建 ARM64 架构 Linux 镜像
        ./build_linux_arm.sh 1.0.0
        
        # 仅在本机试跑调试（原生架构）
        ./build_native.sh 1.0.0
        ```
        构建完成后，带版本号与平台架构后缀的镜像 tar 归档包将固定生成在 `docker/release/` 目录下（例如 `nanzi-ai-agent_1.0.0_linux-amd64_YYYYMMDD.tar`）。

2.  **载入离线镜像包**：
    将下载或自行编译生成的镜像 tar 包拷贝到目标运行服务器上，执行以下命令载入镜像：
    ```bash
    docker load -i nanzi-ai-agent_1.0.0_linux-amd64_YYYYMMDD.tar
    ```
3.  **准备容器环境变量配置文件及 Docker Compose 编排调整**：

    *   **配置环境变量**：
        ```bash
        cd docker
        cp env.example .env
        # 编辑 .env 文件，选择并填入 MySQL 或 PostgreSQL 主库，以及 Redis、Oracle、Jira 配置
        vim .env
        ```
        *注：因容器是网络隔离的沙箱，主库 Host 和 `REDIS_HOST` 均严禁配置为 `localhost` 或 `127.0.0.1`。使用 MySQL 时填写 `MYSQL_HOST`，使用 PostgreSQL 时填写 `POSTGRES_HOST`，可设置为宿主机局域网 IP 或 `host.docker.internal`。*
        *   **`DATABASE_TYPE`（默认 `mysql`）**：选择平台主库类型。设置为 `mysql` 时使用 `MYSQL_*`，设置为 `postgresql` 时使用 `POSTGRES_*`。
        *   **`ENCRYPTION_KEY`（必填）**：用户 API Key 的 Fernet 对称加密密钥（用于加密入库 / 后台解密查看）。MySQL 和 PostgreSQL 都不提供固定管理员凭据，应使用当前密钥现场生成。生成新密钥示例：
            ```bash
            python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
            ```

        ##### 如何创建 / 重建 admin 
        *   **MySQL**：使用当前 `.env` 现场生成管理员和一次性 API Key：
            ```bash
            ./db-prod/create-admin-user.sh
            ./db-prod/create-admin-key.sh admin
            ./db-prod/reset-admin-password.sh admin
            ```
        *   **PostgreSQL**：不使用 MySQL 的 `INIT-USER-ADMIN.sql`，执行以下脚本：
            ```bash
            ./db-prod-pg/create-admin-user.sh
            ./db-prod-pg/create-admin-key.sh
            ./db-prod-pg/reset-admin-password.sh
            ```

    *   **检查与修改 Docker Compose 编排文件（[docker-compose.ai-agent.yml](file:///Users/chenxiaolong/资料/有孚网络/1南孜中台/yovole-nanzi-ai-agent-platform/docker/docker-compose.ai-agent.yml)）**：
        在启动前，您可以根据实际运行环境修改该配置文件：
        1.  **镜像版本校准**：YAML 中默认使用 `image: nanzi-ai-agent:latest`。如果您下载或编译出来的镜像是带具体版本号的（如 `nanzi-ai-agent:1.0.0`），您需要将 YAML 中 `image:` 指向对应标签；或直接在终端为该镜像重新打上 `latest` 标签，即可免除文件修改：
            ```bash
            docker tag nanzi-ai-agent:1.0.0 nanzi-ai-agent:latest
            ```
        2.  **Oracle 客户端挂载卷调整（仅当需要直连 Oracle 数据库时）**：请根据宿主机上 Oracle Instant Client 实际物理存放路径，将 `volumes` 下的 `/app/nanzi-aiagent/lib/instantclient_19_30` 替换为宿主机对应的真实目录。
            *   *低版本 Oracle 数据库兼容提示*：若需要连接低版本 Oracle（如 Oracle 11g 或更低版本），Python 的默认 Thin 模式无法兼容，**必须启用 Thick 模式**（即在 `.env` 中设置 `USE_ORACLE_THICK_MODE=1`），并在此处正确挂载兼容该低版本 Oracle 的物理客户端目录。如果您的智能体不需要操作 Oracle 数据库，此挂载卷配置可直接保留默认或予以注释。
4.  **一键启动与停止服务**：
    平台封装了高内聚的容器启动管理脚本，能自动完成冲突校验与状态检测：
    ```bash
    # 启动 API 容器
    ./start-nanzi-ai-agent.sh
    
    # 停止并移除容器
    ./stop-nanzi-ai-agent.sh
    ```

详细的 Docker 编排配置，请参考：[docker/README.md](file:///Users/chenxiaolong/资料/有孚网络/1南孜中台/yovole-nanzi-ai-agent-platform/docker/README.md)。

---

### 3.4 方案 B：本地源码开发调试部署
适合日常编写业务逻辑、开发调试新功能时采用。

1.  **后端启动 (FastAPI)**：
    ```bash
    # 激活 Python 环境并安装依赖
    source venv/bin/activate
    pip install -r requirements.txt
    
    # 在项目根目录下，拷贝并配置本地 .env 文件
    cp env.example .env
    # 编辑 .env：选择配置 MySQL 或 PostgreSQL，并配置 Redis；ENCRYPTION_KEY 若改动需重新创建 admin
    # MySQL（默认）：DATABASE_TYPE=mysql
    # PostgreSQL：DATABASE_TYPE=postgresql，并填写 POSTGRES_* 参数
    
    # 启动后端 Uvicorn 调试服务
    uvicorn app.main:app --reload --port 8001
    ```
2.  **前端启动 (Vue 3 + Vite)**：
    ```bash
    cd frontend
    npm install
    npm run dev
    ```
    *注：推荐在开发联调时，直接运行项目根目录下的 `./dev.sh` 集成开发脚本，能以前台交互形式一键编译前端并拉起后端，极为高效。*

---

## 4. 登录使用 (Getting Started)

当服务启动成功后，您可以通过浏览器访问管理后台：
*   **管理后台地址**：`http://localhost:8001/`
*   **Swagger 接口文档**：`http://localhost:8001/docs`

### 🔑 首次登录指引
1.  南孜系统后台默认采用 API Key 认证。
2.  **MySQL**：执行 `./db-prod/create-admin-user.sh`；**PostgreSQL**：执行 `./db-prod-pg/create-admin-user.sh`。初始化脚本会按当前 `ENCRYPTION_KEY` 生成随机 API Key，明文只显示一次。
3.  在登录框中粘贴本次生成的 API Key 即可登录后台。仓库不提供默认 API Key，`db-prod/INIT-USER-ADMIN.sql` 已禁用。
4.  **安全提示**：首次登录成功后，请前往**【用户管理】**或【个人中心】设置管理员密码，并将 API Key 存入密钥管理系统；如有暴露风险，立即运行 `create-admin-key.sh` 轮换。

---

## 5. 相关配置初始化 (Configuration Initialization)

首次成功登录系统后，必须前往**【系统配置】**页面完成平台核心配置项的初始化，以保证智能体及各项组件能够正常工作：

### 5.1 大模型配置 (LLM Providers)
*   在【大模型配置】选项卡下，选择或添加您所使用的模型厂商（如 OpenAI, DeepSeek, 阿里百炼/DashScope 等）。
*   配置各厂商对应的 **API Key**、**API Base URL**（如果使用代理或国内镜像端点）以及默认使用的 Model 标识符，供平台各个智能体工作流作为推理底座。

### 5.2 RAGFlow 配置 (RAGFlow Integration)
*   **API 地址 (API URL)**：在【RAGFlow 配置】处，输入您已部署好的 RAGFlow 服务接口地址（注意在 Docker 部署下请写宿主机或局域网 IP，避免使用 localhost）。
*   **接口密钥 (API Key)**：填入在 RAGFlow 控制台中为知识库应用生成的 API Token，使得南孜平台能正常唤醒、同步非结构化知识库并为 ChatBI 数据分析提供文档参考。

### 5.3 数据源管理 (Data Sources)
*   若需使用 ChatBI 智能数据问答与图表可视化，请在【数据源管理】中添加您的业务数据库连接（支持 MySQL、ClickHouse、Oracle 等）。
*   输入连接信息后点击“连通性测试”确保连接无误，智能体将基于此数据源结构进行 SQL 生成与业务指标诊断。

---

## 6. FAQ (常见问题解答)

### Q1: 运行 `build_linux_arm.sh` 或 `build_linux_x86.sh` 编译前端时报 `Killed / cannot allocate memory` 错误
*   **原因**：这是因为在 Mac M 芯片或某些轻量级虚拟机上，使用 Qemu 模拟异构架构（如 `linux/amd64`）执行 Node.js 的 Vite 生产编译时，非常容易产生 CPU 暴涨和内存溢出 (OOM) 导致进程被系统强杀。
*   **解决**：我们已经在构建系统中集成了 **宿主机预构建机制**。在构建异构镜像时，脚本会自动检测宿主机环境，并直接在宿主机进行极速 vite build 编译，跳过容器内模拟编译，彻底避免内存不足错误。请确保您的宿主机已提前安装了 Node.js（`node` 和 `npm` 可执行）。如果想强行在容器内编译，请手动将 Docker Desktop 的可用内存调大至 **8GB 或更大**。

### Q2: 容器启动后自动退出，通过 `docker logs` 查看报错 `Database health check failed`
*   **原因**：在配置 `docker/.env` 文件时，选中的主库 Host 或 `REDIS_HOST` 写了 `localhost` 或 `127.0.0.1`。因为 Docker 容器属于网络隔离沙箱，在容器内部，`localhost` 永远指向容器自身。
*   **解决**：使用 MySQL 时检查 `MYSQL_HOST`，使用 PostgreSQL 时检查 `POSTGRES_HOST`，将其改为宿主机局域网 IP；在 Mac/Windows 的 Docker Desktop 环境下也可使用 `host.docker.internal`。

### Q3: 运行表初始化脚本时报错缺少 `aiomysql` 或 `psycopg`
*   **原因**：未激活 Python 虚拟环境，或未在此虚拟环境下正确运行依赖安装。
*   **解决**：必须先在根目录下激活虚拟环境（`source venv/bin/activate`），运行 `pip install -r requirements.txt`，确保 MySQL 导入所需的 `aiomysql` 或 PostgreSQL 导入所需的 `psycopg` 已安装。

### Q4: 改了 `ENCRYPTION_KEY` 后，已有 admin API Key 登录失败 / 后台解不开 Key
*   **原因**：已经写入数据库的凭据依赖创建时使用的加密密钥；直接更换密钥不会自动重加密存量数据。
*   **解决**：恢复旧密钥完成有审计的密钥轮换，或在确认影响范围后使用对应数据库目录的管理员脚本重新生成凭据：
    ```bash
    source venv/bin/activate
    export PYTHONPATH=.
    python scripts/create_admin_user.py
    # PostgreSQL 也可以直接使用：
    # ./db-prod-pg/create-admin-user.sh
    # ./db-prod-pg/create-admin-key.sh
    # ./db-prod-pg/reset-admin-password.sh
    ```
    保存终端输出的新 API Key 后登录。仓库不提供可恢复的默认管理员 API Key。
