-- 增量：运行对账底稿表 run_reconciliations。
-- 新库由 SQLAlchemy 元数据在启动时自动建表；存量库按下式手工评审执行，不做破坏性自动升级。
CREATE TABLE IF NOT EXISTS run_reconciliations (
 id VARCHAR(36) PRIMARY KEY,
 run_a_id VARCHAR(36) REFERENCES runs(id),
 run_b_id VARCHAR(36) REFERENCES runs(id),
 snapshot JSON NOT NULL,
 created_at TIMESTAMP NOT NULL
);
-- snapshot 在创建时冻结两份运行结果与逐时归因底稿；源数据更新或运行重算不改写旧底稿。
-- 底稿含 schema_version 字段，旧版本运行结果缺少 observations 时接口返回 409，不影响旧运行读取。
