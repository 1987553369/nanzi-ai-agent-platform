-- 固定管理员凭据初始化已永久禁用。
-- 请在配置 ENCRYPTION_KEY 后运行 ./db-prod/create-admin-user.sh；脚本会生成
-- 一次性随机 API Key，明文只在当前终端显示一次。

SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'Fixed admin credentials are disabled; run db-prod/create-admin-user.sh';
