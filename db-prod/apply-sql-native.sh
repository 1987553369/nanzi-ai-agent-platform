#!/usr/bin/env bash
# Compatibility entry point. Safe migration execution requires one long-lived
# database session for advisory locking and checksum-ledger updates.

if [ -z "$BASH_VERSION" ]; then
    exec bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "ℹ️  原生 mysql 多进程导入器已停用：它无法可靠持有数据库全局迁移锁。"
echo "    正在委托给带账本、Checksum 和 advisory lock 的安全执行器。"
exec "$SCRIPT_DIR/apply-sql.sh" "$@"
