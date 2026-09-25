# LOCAL_TASK_AUTHORIZATION

本任务采用离线本地执行方式。GitHub、网页 Planner、浏览器恢复和远端核验不是当前任务前置条件；不访问 GitHub，不执行 fetch/pull/push。`remote_freshness = NOT_CHECKED_OFFLINE`。

当前授权仅覆盖 P0—P3：本地盘点、旧资产登记、协议草案、独立代码、工程测试、合成测试和审批包。未授权 P4 正式历史回测、MT5 经济实验、TRAIN/VALID/OOS、bootstrap、资本敏感性或实盘部署。

旧策略、旧 EA、冻结 EX5、历史协议和旧证据默认只读；不启动 XAMR30，不重跑已关闭实验，不读取保护行情，不修改根目录 AGENTS.md。新内容只写 `research_v2/`。
