#!/bin/bash
# Wrapper to run apply_sql.py with explicit connection parameters.

# 确保脚本在非 bash 环境下（如使用 sh 执行时）能够自动重新唤起并用 bash 执行
if [ -z "$BASH_VERSION" ]; then
    if command -v bash >/dev/null 2>&1; then
        exec bash "$0" "$@"
    else
        echo "❌ 本脚本需要 bash 支持，但系统未找到 bash。"
        exit 1
    fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CALLER_DIR="$PWD"
cd "$ROOT_DIR"


PYTHON_BIN="python3"
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif [[ -x "$ROOT_DIR/venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/venv/bin/python"
fi

SQL_FILES=()
MIGRATION_MODE_ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --baseline-existing)
            MIGRATION_MODE_ARGS+=("$1")
            shift
            continue
            ;;
        --baseline-through|--lock-timeout)
            if [ $# -lt 2 ]; then
                echo "❌ $1 requires a value."
                exit 1
            fi
            MIGRATION_MODE_ARGS+=("$1" "$2")
            shift 2
            continue
            ;;
        --*)
            echo "❌ Unsupported migration option: $1"
            exit 1
            ;;
        *)
            sql_file="$1"
            ;;
    esac
        if [[ "$sql_file" = /* ]]; then
            resolved_sql_file="$sql_file"
        elif [ -f "$CALLER_DIR/$sql_file" ]; then
            resolved_sql_file="$CALLER_DIR/$sql_file"
        elif [ -f "$ROOT_DIR/$sql_file" ]; then
            resolved_sql_file="$ROOT_DIR/$sql_file"
        elif [ -f "$SCRIPT_DIR/$sql_file" ]; then
            resolved_sql_file="$SCRIPT_DIR/$sql_file"
        else
            resolved_sql_file="$sql_file"
        fi
        SQL_FILES+=("$resolved_sql_file")
        shift
done

RUN_ALL=false
if [ ${#SQL_FILES[@]} -eq 0 ]; then
    RUN_ALL=true
    while IFS= read -r sql_file; do
        SQL_FILES+=("$sql_file")
    done < <(find "$SCRIPT_DIR" -maxdepth 1 -type f -name 'V*.sql' -print | sort -V)
fi

if [ ${#SQL_FILES[@]} -eq 0 ]; then
    echo "❌ No SQL files found."
    exit 1
fi

read -r -p "MySQL host [localhost]: " MYSQL_HOST_INPUT
read -r -p "MySQL port [3306]: " MYSQL_PORT_INPUT
read -r -p "MySQL user: " MYSQL_USER_INPUT
read -r -s -p "MySQL password: " MYSQL_PASSWORD_INPUT
echo
read -r -p "Target database: " MYSQL_DATABASE_INPUT

MYSQL_HOST_INPUT=${MYSQL_HOST_INPUT:-localhost}
MYSQL_PORT_INPUT=${MYSQL_PORT_INPUT:-3306}

if [ -z "$MYSQL_USER_INPUT" ] || [ -z "$MYSQL_DATABASE_INPUT" ]; then
    echo "❌ User、Target database 都必须手动输入。"
    exit 1
fi

echo "---------------------------------------------------"
echo "请确认本次 SQL 执行目标："
echo "  Host     : $MYSQL_HOST_INPUT"
echo "  Port     : $MYSQL_PORT_INPUT"
echo "  User     : $MYSQL_USER_INPUT"
echo "  Database : $MYSQL_DATABASE_INPUT"
echo "  Password : ******"
echo "  SQL files: ${SQL_FILES[*]}"
if [ ${#MIGRATION_MODE_ARGS[@]} -gt 0 ]; then
    echo "  Migration mode: ${MIGRATION_MODE_ARGS[*]}"
fi
read -r -p "确认无误请输入 YES 继续执行：" CONFIRM_INPUT
CONFIRM_UPPER=$(echo "$CONFIRM_INPUT" | tr '[:lower:]' '[:upper:]')
if [ "$CONFIRM_UPPER" != "YES" ]; then
    echo "❌ 已取消，未执行 SQL。"
    exit 1
fi

COMMON_ARGS=(
    --host "$MYSQL_HOST_INPUT"
    --port "$MYSQL_PORT_INPUT"
    --user "$MYSQL_USER_INPUT"
    --database "$MYSQL_DATABASE_INPUT"
    --yes
)

IMPORT_ARGS=("${COMMON_ARGS[@]}")
if [ ${#MIGRATION_MODE_ARGS[@]} -gt 0 ]; then
    IMPORT_ARGS+=("${MIGRATION_MODE_ARGS[@]}")
fi
IMPORT_ARGS+=("${SQL_FILES[@]}")

echo "---------------------------------------------------"
echo "🚀 校验迁移清单并在单一数据库锁内执行..."
if ! NANZI_MIGRATION_PASSWORD="$MYSQL_PASSWORD_INPUT" \
    "$PYTHON_BIN" "$SCRIPT_DIR/apply_sql.py" \
    "${IMPORT_ARGS[@]}"; then
    echo "❌ 数据库迁移失败。"
    exit 1
fi

if [ "$RUN_ALL" = true ]; then
    echo "---------------------------------------------------"
    echo "✅ 所有数据库结构初始化迁移 SQL 文件执行成功。"
    
    # 交互询问是否创建随机管理员凭据
    read -r -p "是否需要创建默认管理员 admin 并生成一次性随机 API Key？ [Y/N]: " RUN_INIT_ADMIN
    RUN_INIT_ADMIN_UPPER=$(echo "$RUN_INIT_ADMIN" | tr '[:lower:]' '[:upper:]')
    if [ "$RUN_INIT_ADMIN_UPPER" == "Y" ] || [ "$RUN_INIT_ADMIN_UPPER" == "YES" ]; then
        echo "---------------------------------------------------"
        echo "🚀 正在生成默认管理员和一次性随机 API Key..."
        if ! DATABASE_TYPE=mysql \
            MYSQL_HOST="$MYSQL_HOST_INPUT" \
            MYSQL_PORT="$MYSQL_PORT_INPUT" \
            MYSQL_USER="$MYSQL_USER_INPUT" \
            MYSQL_PASSWORD="$MYSQL_PASSWORD_INPUT" \
            MYSQL_DB="$MYSQL_DATABASE_INPUT" \
            python3 scripts/create_admin_user.py; then
            echo "❌ 默认管理员账号创建失败。"
            exit 1
        fi
        echo "✅ 管理员初始化完成；请立即保存终端中仅显示一次的 API Key。"
    else
        echo "💡 已跳过默认管理员账号数据的导入。"
    fi
else
    echo "💡 SQL 执行完成。管理员请使用 ./db-prod/create-admin-user.sh 单独创建。"
fi
