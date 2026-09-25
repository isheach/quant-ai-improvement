# 可直接交给本地执行者的 WF3 启动提示词

你继续使用原工作文件夹，但不再沿用旧 Python 快速回放流程。首先完整读取同目录 MASTER_PLAN.md 与 WINDOWS.csv。MASTER_PLAN是新方向的唯一总协议；旧审批不授权新任务。

## 1. 本次只执行 S0

目标：准备 MT5 原生 XAUUSDm 的趋势/受限网格两套独立 EA、真实风险和审计、一月步长6/3/3窗口、可恢复运行器；最多分别执行一次限定的MT5工程smoke。完成开工包后停止，等待一次批准再启动三窗口收益研究。

不做新的参数扫描，不运行S1之后的研究，不重跑旧XAMR30/R12—R24，不实盘。不能因为MASTER_PLAN列出了完整路线，就把所有后续步骤当成当前授权。

用户已经把WF3研究范围改为2024-01-01～2026-06-30，不要再用旧截止2024-05的门槛错误阻塞WF3；但不得追溯改变旧实验记录。2026-07及之后不分析。2023Q4仅限总计划规定的过去指标预热。

## 2. 实际目录与Git

检查当前目录、研究根目录、Git根目录、HEAD、分支、工作区和已运行的MT5/Python进程。历史项目可能有 `新量化策略/research_v2` 和 `_repo_量化交易ai改进/research_v2` 两份：先比较协议、代码和状态哈希；明确哪份执行、哪份Git镜像，不静默覆盖、不创建第三份。

Planner写计划前审核基线为492e15c1b847f32d2d7295f08a9647ec386c3dd4；写入本计划会产生一个更新提交，因此不能要求HEAD仍等于该旧SHA。以实际包含本计划的最新研究分支为准。

研究分支仍为 `repair/xamr30-v1-daily-r1`，不要切回陈旧main。网络可用时仅普通fetch/fast-forward同步；有分叉或他人改动保留并报告，不reset、不merge/rebase、不force。API不能访问GitHub不阻止本地工作；本地文件已是新版就直接继续。

本次只写 `research_v2/mt5_wf_v3/` 及新EA明确命名空间。保留所有旧报告、源码、EX5和原始数据。不执行旧runner中先删报告/清空audit的操作。

## 3. 建立可恢复状态

在mt5_wf_v3创建：
- STATUS.json：当前步骤、已完成项、活动run、真实启动次数、阻塞、下一步；
- EVENTS.jsonl：追加事件，真实UTC时间，未知的旧时间不补造；
- RUNS.jsonl：任务与尝试台账；
- runs/<run_id>/：预先manifest、INI安全副本、执行命令摘要、stdout/stderr、ledger、结果、hash；
- LATEST_REPORT.md：只保留一份清晰当前摘要，历史报告保存在run下。

启动前先预留run与独立目录，记录PID+创建时间+程序路径，单实例锁；断线先检查任务是否还在跑。已经完成不重跑，UNKNOWN不擅自删除或重新启动。任何新的attempt必须记录缘由并仍受S0预算约束。

不再复制二十个互相矛盾的状态文件。根目录旧CURRENT_STATUS属于旧项目快照，不作为WF3批准来源。

## 4. 旧机制映射与新EA

完整检查旧eva028代表源码，建立LEGACY_MECHANISM_MAP.md，列出EMA/斜率/突破、Vol-Gate单位与滞后、网格基线、篮子止损、日损、高水位和周末保护的原位置及新实现。

按MASTER_PLAN第8—10节实现T和G；不是再写简化Python模型。使用新EA名字，如WF3_XAU_Trend和WF3_XAU_Grid，以及独立magic。两者共用MQL5成交、OCP风险、资金、日志模块，优化时不关闭必要审计。

先落实：真实quantity、最小手拒单、实际初始SL风险、篮子风险冻结、Bid/Ask、止损/跳空、持仓时间、未成交订单、日损、权益高水位、session/周末保护。没有margin/spec依据不能硬编码假定通过。G无法满足500美元最小手数时明确不可行，不增风险或自动换本金。

第一批8个T与8个G配置按总计划固定；不要因为某候选看起来太简单而添加新维度。T与G本次不组合。纯工程测试使用合成固定报价可以用Python手算核对，但不得拿它生成历史策略收益。

每个input给出单位、作用函数、生效开关。源默认值、显式配置、resolved INI、运行manifest做自动类型化一致性检查；不是检查文件存在就PASS。

## 5. 原生数据与测试身份

只允许真实券商品种XAUUSDm，SYMBOL_CUSTOM必须false；禁止XAUUSD_HIST、CustomSymbol、CSV回灌。只启动指定的本地Strategy Tester，不交易真实账户、不用付费云代理。

读取并保存必要的非敏感规格：digits/point/tick_size、合约、交易量min/step/max、账户模式、保证金、佣金与swap设置、服务器时间映射、sessions。隐藏账户登录、token与密码。

先用MT5已有原生历史；如缺所需历史，可正常同步本阶段/计划允许的过去报价，不另写数据探针或把本地CSV导入品种。平台缓存可能更广，但EA/Python不得分析许可区间外数据。检查真实tick覆盖；未知不能以99%质量数代替。

工程smoke固定Model=4。缺失fallback、实际区间缩短或异常都明确标注。不得静默切换Model=1/2或Python来通过。

## 6. S0工程验证与运行预算

先编译新EA及运行合成/静态测试：多空现金流、入场/平仓费用、OCP初始风险、向下手数、网格两层总风险、下一tick下单、未来信息不影响过去、跨月不重置高水位、状态参数锁定、窗口结束exclusive、防重复和恢复。

全部必要前置合格后允许工程smoke：
- T anchor：2024-01-01 <= t < 2024-02-01，500 USD，1:200，Model4，最多一次启动；
- G anchor：同区间/模式/资金，最多一次启动。

smoke可以产生实际Tester交易，但收益只用于现金对账，不用于选参数或宣布策略成立；这两个运行标ENGINEERING_ONLY。报告启动次数由台账统计，不在模板预填0。

若没有信号，报告真实零成交和漏斗，不能写成交链通过；若G因最小手拒单，报告ACCOUNT_FEASIBILITY_FAIL，不托底。任何崩溃/未知执行状态停止对应任务；本提示词不授权第三次MT5启动。可继续完成不受影响的代码与文档，不无限空等。

MT5原报告、订单/deals、佣金/swap/fee及权益对账：入场与出场费用都计入；最终无活动仓位/订单；gross/net与报告一致，货币误差<=0.01 USD或仅有明确报告舍入的解释。日内权益与balance分开。运行source/EX5/INI前后身份一致。

## 7. 自动验证滚动日历与未来计划

验证WINDOWS.csv：19个FULL_6_3_3、2个尾部更新；每窗训练6月/验证3月；完整测试3月；尾部2月/1月；月度部署起点严格递增且不重叠，总21月，末端exclusive=2026-07-01。

准备三窗口S1计划，只W01—W03；每家族总上限39passes（包含已完成的对应smoke），其中训练24、验证<=9、测试诊断<=3、连续更新账户与固定anchor账户各1。参数数不等于执行数；Cash和重复身份任务不重复启动。

实现选择器：只读取MT5训练/验证结果；训练取2名+符合条件incumbent，最多3名；验证锁1名或Cash，参照MASTER_PLAN明确门槛/Q/稳定规则。测试文件目录不允许选择器打开。先生成整段参数日程及decision_asof，再执行测试。月度账户连续管理仓位，不能简单相加重叠三个月利润。

本阶段只生成PLANNED任务，不执行训练/验证/测试；新APPROVAL中的S1执行授权保持false。生成器不得自行给自己批准。

## 8. 输出开工包

交付：
LEGACY_MECHANISM_MAP.md
ENGINE_AND_DATA_IDENTITY.json
STRATEGY_INPUTS.json
S0_TEST_RESULTS.json
S0_SMOKE_RECONCILIATION.json
S1_PILOT_TASKS.PLANNED.jsonl
S0_READINESS.md
及每次真实smoke的完整证据。

S0_READINESS必须分别说明：数据与成本身份、T工程、G工程、500美元可行性、运行恢复、尚未解决问题。未知项不以PARTIAL模板冒充PASS。

第一小目标：用户能看到一个真正的MT5原生品种运行，从报告追溯到每笔交易与全部参数；下一步能在同一系统内跑有限三窗口，而不是再看到另一套Python收益。

## 9. 提交与结束

Git只stage本阶段目录及授权的新源代码，不add .，不提交原始大型tick缓存、私有配置或账号。建议commit：`WF3: prepare native MT5 walk-forward pilot`。

网络可用且研究分支没有并发新提交时，普通fast-forward push到同一研究分支，不动main。不可用则本地commit并如实记录。

最终用中文报告：真实HEAD/分支、工作目录、原生symbol/Model、MT5实际启动次数、工程是否闭合、所有报告位置、阻塞、小试任务数量与hash、push状态。完成S0后停止，不自动开始S1。

中断恢复先读STATUS/EVENTS/RUNS和活动run，再继续未完成且已授权的子步骤；不得从旧聊天或旧approved=true恢复已经被WF3替代的工作。
