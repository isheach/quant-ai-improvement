# Stage 0 R3 · 数据暴露登记（`data_exposure_register.md`）

依据：GPT 第二批裁定 §三 R0 第 6 条。**目的：明确区分「本轮未跑」与「项目历史已跑」。**

## 1. 三段定义

| 区间 | 名称 | 状态 |
|---|---|---|
| 各品种起点 ～ 2024-05-31 | `train` | 可用 |
| 2024-06-01 ～ 2025-05-31 | `valid` | 可用 |
| **2025-06-01 ～ 2026-05-31** | **`exposed_oos`** | **★历史已跑，不再是干净样本外** |
| **2026-06-01 ～ 2026-09-30** | **`user_holdout`** | **★硬禁止（用户保留）** |

**★关键更正（GPT §1.4）**：
> 「本轮阶段 E 未跑」**不等于**「项目从未跑过该段」。
> 实测：**113 份 INI 与 2025-06-01~2026-05-31 重叠** → 该段统一标 `exposed_oos`。

## 2. 与 `exposed_oos` 重叠的 INI（113 份）

| ini | 品种 | from | to | expert |
|---|---|---|---|---|
| `run_BS75_test.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BS75f.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BS75t2.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-057.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_TrendCore |
| `run_BT_btc-058.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_TrendCore |
| `run_BT_btc-059.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_TrendCore |
| `run_BT_btc-106.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-107.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-108.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-109.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-112.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-113.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-114.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-115.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-116.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-118.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-123.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-125.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-133.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-134.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-135.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-139.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-140.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-141.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-142.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-145.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-146.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-148.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-149.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-150.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-151.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-152.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-153.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-156.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-157.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-158.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-160.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-163.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-165.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-166.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-168.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-169.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-172.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-173.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-174.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-175.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-180.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-181.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-183.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-184.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-188.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-193.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-195.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-196.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-197.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-198.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-199.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-203.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-204.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| `run_BT_btc-205.ini` | BTCUSDm | 2025-06-01 | 2026-05-31 | dshtrend\dsh_BtcSwing |
| …（其余 53 份见 CSV） | | | | |

## 3. 与 `user_holdout`（2026-06~09）重叠的 INI（10 份）

| ini | 品种 | from | to | expert |
|---|---|---|---|---|
| `run_att_valid_confirm1.ini` | XAUUSD_HIST | 2025-01-02 | 2026-06-30 | eva028\eva028_VolumetricPulseGrid_CoreRisk |
| `run_att_valid_gateoff.ini` | XAUUSD_HIST | 2025-01-02 | 2026-06-30 | eva028\eva028_VolumetricPulseGrid_CoreRisk |
| `run_att_valid_trendoff.ini` | XAUUSD_HIST | 2025-01-02 | 2026-06-30 | eva028\eva028_VolumetricPulseGrid_CoreRisk |
| `run_base_locked_valid.ini` | XAUUSD_HIST | 2025-01-02 | 2026-06-30 | eva028\eva028_VolumetricPulseGrid_CoreRisk |
| `run_d_k25_valid.ini` | XAUUSD_HIST | 2025-01-02 | 2026-06-30 | eva028\eva028_VolumetricPulseGrid_CoreRisk |
| `run_d_koff_valid.ini` | XAUUSD_HIST | 2025-01-02 | 2026-06-30 | eva028\eva028_VolumetricPulseGrid_CoreRisk |
| `run_v_baseline.ini` | XAUUSD_HIST | 2025-01-02 | 2026-06-30 | eva028\eva028_VolumetricPulseGrid_CoreRisk |
| `run_v_locked.ini` | XAUUSD_HIST | 2025-01-02 | 2026-06-30 | eva028\eva028_VolumetricPulseGrid_CoreRisk |
| `run_v_locked_k25.ini` | XAUUSD_HIST | 2025-01-02 | 2026-06-30 | eva028\eva028_VolumetricPulseGrid_CoreRisk |
| `run_v_locked_off.ini` | XAUUSD_HIST | 2025-01-02 | 2026-06-30 | eva028\eva028_VolumetricPulseGrid_CoreRisk |

**★全部为 `eva028` 线产物**（详见 `公共部分\约束违规记录_eva028_20260913.md`）。
**按 GPT Q4：保持用户原日期定义并继续硬禁止，同时登记历史暴露；不擅自顺延、不删除证据。**

## 4. 本轮（R0 之后）的承诺

```
· 所有 run 必须先登记（run_registry.jsonl），未登记不启动 MT5
· 与 user_holdout 有任何重叠 → 编排器【直接拒绝启动】
· 与 exposed_oos 重叠 → 需显式 allow_exposed_oos=True，并标 dataset_role=exposed_oos
· 品种不在白名单 → 拒绝启动
· run_id 重复 / 目录已存在 / 报告名已存在 → 拒绝覆盖
```

## 5. 产物

- `data_exposure_register.md`（本文件）
- `data_exposure.csv`（113 行）
- `run_registry.jsonl`（登记表，只追加）
- `r0_guard.py`（护栏实现，含自检）

