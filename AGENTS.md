# Planner–Executor 工作协议

本仓库采用固定的 Planner–Executor 工作模式：

- Web ChatGPT 是 authoritative Planner / Thinker，负责读取 GitHub 最新状态、制定下一阶段、给出验收标准与禁止事项。
- Local Codex 是 Executor，负责在本地工作区内按 Planner 的当前指令执行、验证并回报证据。
- 当前 Planner 的会话信息只能从 `.codex/planner.json` 读取；不得在本文件或代码中硬编码个人 ChatGPT conversation URL。该配置是本机私有配置，不能提交到 Git。

## 标准循环

每个阶段必须按以下顺序闭环：

1. Planner 查看 GitHub 最新状态。
2. Planner 在同一 conversation 中给出唯一的 `<Start>...<End>` 下一阶段指令。
3. Codex 读取并确认当前指令，在其边界内执行。
4. Codex 运行该阶段要求的测试或实验，并保存可复核证据。
5. Codex 检查 `git diff`、`git diff --check` 和工作区状态。
6. Codex 只提交预期文件，创建清晰的 commit。
7. 在得到相应授权后，Codex push 到指定远端，并 fetch/核对本地 HEAD 与远端状态。
8. Codex 回到同一 Planner conversation，让 Planner 重新查看 GitHub 最新状态。
9. Planner 再给出下一阶段；未获得新的完成指令前，不得自行进入下一阶段。

阶段只有在“验证通过、差异检查通过、commit 完成、push 已核对、同一 Planner 已看到最新状态”全部成立时才算完成。

## Planner conversation 与浏览器恢复

- 新会话启动时，先读取并校验 `.codex/planner.json` 的 `planner`、`thread_url`、`conversation_id`、`planner_model`、`planner_reasoning` 和 `repository` 字段；缺失或无效时停止并报告，不得猜测会话地址或创建替代 conversation。
- 始终复用配置指向的同一 Planner conversation。使用一个持久浏览器标签；标签丢失、脱离或页面内容陈旧时，按 `conversation_id`/`thread_url` 恢复并核对当前会话，再继续读取。
- 恢复时先读取页面中可见的最新用户消息和 Planner 回复；不要因为一次读取为空、陈旧或超时就重复发送。
- 不把环境中偶然打开的其他 ChatGPT 页面当作 Planner，也不因恢复失败而新建 conversation。

## Single-submit 与 completion gate

- 每个 Planner 阶段请求只能提交一次。提交后等待页面完成，并通过可见消息确认是否已提交；不得因轮询结果陈旧或 DOM 未刷新而重复提交。
- 如果无法确定消息是否已经提交，先恢复/读取同一 conversation，确认最新用户消息和回复中是否已有该请求；只有确认不存在时才允许再次提交。
- Codex 只有在当前回合的 Planner 回复完整可见、没有错误或截断，并且包含唯一、明确的 `<Start>...<End>` 指令块时，才通过 completion gate。
- 缺少完整指令块、指令来自旧回合、页面仍在生成或内容不确定时，停止执行并先恢复读取或报告阻塞；不得把旧指令拼接成新阶段。

## Planner / Executor boundary

- Planner 决定阶段目标、范围、参数、验收标准和禁止事项；Codex 不自行扩展研究问题、修改策略意图或改变参数。
- Codex 可以执行完成当前指令所需的常规安全子步骤（检查、编辑、测试、实验、差异检查、commit、push 和证据整理），但不能把下一阶段工作当作当前阶段的隐含授权。
- 未获得当前 Planner `<Start>...<End>` 明确授权，不运行 MT5 经济实验、TRAIN/VALID、bootstrap、OOS/holdout、资本敏感性或其他会产生策略经济结论的工作。
- Codex 只报告可复核事实、测试结果、提交状态和阻塞原因；研究判断与下一阶段决策仍由 Planner 作出。

## Git safety

- 修改前检查当前分支、远端、`git status --short --branch` 和已有用户改动；保留与本任务无关的改动，不覆盖或清理用户文件。
- 不使用 `git reset --hard`、`git checkout --` 或无边界删除来“整理”工作区。目标不明确时停止并报告。
- 只 stage 当前 Planner 指令允许的文件。提交前运行相关测试、`git diff --check`，并检查 staged 文件清单；研究代码、数据冻结证据和历史验证产物未经明确授权不得改写。
- `.codex/planner.json` 含个人会话信息，必须保持未跟踪/被忽略，绝不能 `git add`、commit、push 或复制到公开日志。
- push 后使用 `git fetch` 和明确的 commit/分支核对确认远端已更新；若 push 被安全策略或权限阻止，不绕过策略，报告本地 commit 与阻塞状态。

## 启动规则

新的 Codex session 应先读取本文件和 `.codex/planner.json`，恢复同一 Planner conversation，读取最新 `<Start>...<End>` 指令，然后才开始执行。整个流程必须持续使用同一 Planner conversation，直至 Planner 明确结束或切换阶段。
