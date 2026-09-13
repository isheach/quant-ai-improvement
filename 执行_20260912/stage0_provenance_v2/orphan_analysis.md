# 阶段 A 补漏 · 绕过 JSONL 协议的 run

## 发现

`P4C*` / `P4D*` / `S1CHK*` / `S1SIG` 这批 run 是我**直接用 `runexp.py`** 跑的：
它们有 `run_<tag>.ini` 与审计 CSV，但**没有写入任何 `inbox/outbox`** → 
v1 与 v2 都扫不到它们。**这是「绕过协议」的真实缺口。**

## 修法

不再依赖 JSONL，改为**从 `mql5\config\run_*.ini` 反查全部 run**（文件链为准）。

| 项 | 值 |
|---|---|
| `run_*.ini` 总数 | **655** |
| 其中已在 v2 中 | 469 |
| **★v2 漏掉的（orphan）** | **186** |

## 漏掉的 run（186 条）

| run_tag | 品种 | 入金 | 模型 | 审计行 | position_id | 报告 | 留白 | 超配 |
|---|---|---|---|---:|---|---|---|---|
| `BS75_test` | BTCUSDm | 300 | 2 |  | 0 | 1 | no | 1 |
| `BS75_train` | BTCUSDm | 300 | 2 |  | 0 | 1 | no | 1 |
| `BS75_valid` | BTCUSDm | 300 | 2 |  | 0 | 1 | no | 1 |
| `BS75f` | BTCUSDm | 300 | 2 | 69 | 0 | 1 | no | 1 |
| `BS75t2` | BTCUSDm | 300 | 2 | 3 | 0 | 1 | no | 1 |
| `BS75tr2` | BTCUSDm | 300 | 2 | 671 | 0 | 1 | no | 1 |
| `BS75va2` | BTCUSDm | 300 | 2 | 77 | 0 | 1 | no | 1 |
| `Bfix22a` | BTCUSDm | 300 | 2 | 37320 | 0 | 1 | no | 1 |
| `Bfix22b` | BTCUSDm | 300 | 2 | 37945 | 0 | 1 | no | 1 |
| `C094_t` | BTCUSDm | 300 | 2 | 69 | 0 | 1 | no | 1 |
| `C094_v` | BTCUSDm | 300 | 2 | 77 | 0 | 1 | no | 1 |
| `C099_t` | BTCUSDm | 300 | 2 | 65 | 0 | 1 | no | 1 |
| `C099_v` | BTCUSDm | 300 | 2 | 65 | 0 | 1 | no | 1 |
| `C100_t` | BTCUSDm | 300 | 2 | 46 | 0 | 1 | no | 1 |
| `C100_v` | BTCUSDm | 300 | 2 | 37 | 0 | 1 | no | 1 |
| `DD_eval` | BTCUSDm | 300 | 2 | 37320 | 0 | 1 | no | 1 |
| `DD_hard` | BTCUSDm | 300 | 2 | 287 | 0 | 1 | no | 1 |
| `Gfix32` | XAUUSDm | 300 | 2 | 4403 | 0 | 1 | no | 1 |
| `JP_jpy-047` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-048` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-049` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-050` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-051` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-052` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-053` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-054` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-055` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-056` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-057` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-058` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-059` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-060` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-061` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-062` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-063` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-064` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-065` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-066` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-067` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-068` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-069` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `JP_jpy-070` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 0 |
| `Jtst` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 1 |
| `LAT0` | BTCUSDm | 300 | 2 |  | 0 | 1 | no | 1 |
| `LAT300` | BTCUSDm | 300 | 2 |  | 0 | 1 | no | 1 |
| `LAT800` | BTCUSDm | 300 | 2 |  | 0 | 0 | no | 1 |
| `LATCHK_btcswing` | BTCUSDm | 300 | 2 |  | 0 | 0 | no | 1 |
| `LATCHK_jpyrev` | BTCUSDm | 300 | 2 |  | 0 | 0 | no | 1 |
| `LATCHK_meanrev` | BTCUSDm | 300 | 2 |  | 0 | 0 | no | 1 |
| `LATCHK_trend` | BTCUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `MO_all` | BTCUSDm | 300 | 2 | 164 | 0 | 1 | no | 1 |
| `MO_hi` | BTCUSDm | 300 | 2 | 19 | 0 | 1 | no | 1 |
| `MO_lo` | BTCUSDm | 300 | 2 | 26 | 0 | 1 | no | 1 |
| `MOall_t` | BTCUSDm | 300 | 2 | 50 | 0 | 1 | no | 1 |
| `MOall_v` | BTCUSDm | 300 | 2 | 36 | 0 | 1 | no | 1 |
| `MOlo_t` | BTCUSDm | 300 | 2 | 6 | 0 | 1 | no | 1 |
| `MOlo_v` | BTCUSDm | 300 | 2 | 5 | 0 | 1 | no | 1 |
| `MRbase` | BTCUSDm | 300 | 2 | 294 | 0 | 1 | no | 1 |
| `OV10k_t` | BTCUSDm | 10000 | 2 | 120 | 0 | 1 | no | 1 |
| `OV10k_v` | BTCUSDm | 10000 | 2 | 113 | 0 | 1 | no | 1 |
| `OV_10k` | BTCUSDm | 10000 | 2 | 671 | 0 | 1 | no | 1 |
| `OV_off` | BTCUSDm | 300 | 2 | 671 | 0 | 1 | no | 0 |
| `P4C1_train` | BTCUSDm | 500 | 2 | 546 | 1 | 1 | no | 1 |
| `P4C1_valid` | BTCUSDm | 500 | 2 | 95 | 1 | 1 | no | 1 |
| `P4C2_train` | BTCUSDm | 500 | 2 | 1460 | 1 | 1 | no | 1 |
| `P4C2_valid` | BTCUSDm | 500 | 2 | 167 | 1 | 1 | no | 1 |
| `P4C3_train` | BTCUSDm | 500 | 2 | 323 | 1 | 1 | no | 1 |
| `P4C3_valid` | BTCUSDm | 500 | 2 | 55 | 1 | 1 | no | 1 |
| `P4D1000` | BTCUSDm | 1000 | 2 | 101 | 1 | 1 | no | 1 |
| `P4D2000` | BTCUSDm | 2000 | 2 | 99 | 1 | 1 | no | 1 |
| `P4D400` | BTCUSDm | 400 | 2 | 74 | 1 | 1 | no | 1 |
| `P4D450` | BTCUSDm | 450 | 2 | 86 | 1 | 1 | no | 1 |
| `P4D550` | BTCUSDm | 550 | 2 | 95 | 1 | 1 | no | 1 |
| `P4D600` | BTCUSDm | 600 | 2 | 97 | 1 | 1 | no | 1 |
| `P4D700` | BTCUSDm | 700 | 2 | 100 | 1 | 1 | no | 1 |
| `RV_off` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 1 |
| `RV_on` | USDJPYm | 300 | 2 |  | 0 | 0 | no | 1 |
| `S1CHK` | BTCUSDm | 500 | 2 | 104 | 1 | 1 | no | 1 |
| `S1CHK2` | BTCUSDm | 500 | 2 | 99 | 1 | 1 | no | 1 |
| `S1SIG` | BTCUSDm | 500 | 2 | 36 | 1 | 1 | no | 1 |
| `T0` | BTCUSDm | 300 | 2 |  | 0 | 1 | no | 1 |
| `T1` | BTCUSDm | 300 | 2 |  | 0 | 1 | no | 1 |
| `T48` | BTCUSDm | 300 | 2 | 92 | 0 | 1 | no | 1 |
| `T5` | BTCUSDm | 300 | 2 |  | 0 | 1 | no | 1 |
| `TR48k` | BTCUSDm | 1000 | 2 | 1069 | 0 | 1 | no | 1 |
| `V48` | BTCUSDm | 300 | 2 | 162 | 0 | 1 | no | 1 |
| `VZfalse` | BTCUSDm | 300 | 2 |  | 0 | 1 | no | 1 |
| `VZtrue` | BTCUSDm | 300 | 2 |  | 0 | 1 | no | 1 |
| `att_valid_confirm1` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | YES | 0 |
| `att_valid_gateoff` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | YES | 0 |
| `att_valid_trendoff` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | YES | 0 |
| `b0_locked` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `b0_norisk` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `b1_baseline` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `b1a_pure_grid` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `b1b_pure_trend` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `b1c_cut_on` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `b2_basket10` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `b2_basket15` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `b2_basket20` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `b3_grid25k` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `b3_grid30k` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `base_locked` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `base_locked_valid` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | YES | 0 |
| `d_k25_valid` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | YES | 0 |
| `d_koff_valid` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | YES | 0 |
| `d_locked_k25` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `d_locked_k40` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `d_locked_nodaily` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `d_locked_off` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `diag_grid_audit` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `diag_pure_grid_audit` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `g000_EntryS1p5_StopSi3p0_ExitSi0p0_MaxBar48` | BTCUSDm | 300 | 2 | 352 | 0 | 1 | no | 1 |
| `g001_EntryS1p5_StopSi3p0_ExitSi0p5_MaxBar48` | BTCUSDm | 300 | 2 | 336 | 0 | 1 | no | 1 |
| `g002_EntryS1p5_StopSi4p0_ExitSi0p0_MaxBar48` | BTCUSDm | 300 | 2 | 277 | 0 | 1 | no | 1 |
| `g003_EntryS1p5_StopSi4p0_ExitSi0p5_MaxBar48` | BTCUSDm | 300 | 2 | 284 | 0 | 1 | no | 1 |
| `g004_EntryS2p0_StopSi3p0_ExitSi0p0_MaxBar48` | BTCUSDm | 300 | 2 | 242 | 0 | 1 | no | 1 |
| `g005_EntryS2p0_StopSi3p0_ExitSi0p5_MaxBar48` | BTCUSDm | 300 | 2 | 240 | 0 | 1 | no | 1 |
| `g006_EntryS2p0_StopSi4p0_ExitSi0p0_MaxBar48` | BTCUSDm | 300 | 2 | 195 | 0 | 1 | no | 1 |
| `g007_EntryS2p0_StopSi4p0_ExitSi0p5_MaxBar48` | BTCUSDm | 300 | 2 | 197 | 0 | 1 | no | 1 |
| `g008_EntryS2p5_StopSi3p0_ExitSi0p0_MaxBar48` | BTCUSDm | 300 | 2 | 149 | 0 | 1 | no | 1 |
| `g009_EntryS2p5_StopSi3p0_ExitSi0p5_MaxBar48` | BTCUSDm | 300 | 2 | 145 | 0 | 1 | no | 1 |
| `g010_EntryS2p5_StopSi4p0_ExitSi0p0_MaxBar48` | BTCUSDm | 300 | 2 | 114 | 0 | 1 | no | 1 |
| `g011_EntryS2p5_StopSi4p0_ExitSi0p5_MaxBar48` | BTCUSDm | 300 | 2 | 116 | 0 | 1 | no | 1 |
| `g012_EntryS3p0_StopSi3p0_ExitSi0p0_MaxBar48` | BTCUSDm | 300 | 2 | 105 | 0 | 1 | no | 1 |
| `g013_EntryS3p0_StopSi3p0_ExitSi0p5_MaxBar48` | BTCUSDm | 300 | 2 | 103 | 0 | 1 | no | 1 |
| `g014_EntryS3p0_StopSi4p0_ExitSi0p0_MaxBar48` | BTCUSDm | 300 | 2 | 85 | 0 | 1 | no | 1 |
| `g015_EntryS3p0_StopSi4p0_ExitSi0p5_MaxBar48` | BTCUSDm | 300 | 2 | 86 | 0 | 1 | no | 1 |
| `g_full_z2000` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `g_full_z3000` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `g_full_z5000` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `g_full_z7000` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `g_pg_z1000` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `g_pg_z10000` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `g_pg_z2000` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `g_pg_z3000` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `g_pg_z5000` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `g_pg_z7000` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_bo20` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_bo45` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_bo60` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_confirm1` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_confirm5` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_fast10` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_fast30` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_gateoff` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_gridon` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_rv15` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_rv25` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_sl25` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_sl50` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_slow100` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_slow40` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_trail20` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `s_trail45` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `smoke` | XAUUSD_HIST | 500 | 2 | 4 | 0 | 1 | no | 0 |
| `t_nocut` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `t_notrendexit` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `t_tp` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `t_tp15` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | no | 0 |
| `v_baseline` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | YES | 0 |
| `v_locked` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | YES | 0 |
| `v_locked_k25` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | YES | 0 |
| `v_locked_off` | XAUUSD_HIST | 500 | 2 |  | 0 | 1 | YES | 0 |
| `黄金_gold-001` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-002` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-003` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-004` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-005` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-006` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-007` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-008` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-009` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-010` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-011` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-012` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-013` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-014` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-015` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-016` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 1 |
| `黄金_gold-017` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 1 |
| `黄金_gold-018` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 1 |
| `黄金_gold-019` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 1 |
| `黄金_gold-020` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-021` | XAUUSDm | 300 | 2 |  | 0 | 0 | no | 0 |
| `黄金_gold-022` | XAUUSDm | 1000 | 2 |  | 0 | 0 | no | 0 |

**★其中审计含 `position_id` 列（= 新格式、可对账）：16 / 186**

| 入金分布 | 值 |
|---|---|
| 300 | 105 |
| 500 | 69 |
| 10000 | 3 |
| 1000 | 3 |
| 2000 | 1 |
| 400 | 1 |
| 450 | 1 |
| 550 | 1 |
| 600 | 1 |
| 700 | 1 |

## manifest 追加（只追加，旧行不动）

| 项 | 值 |
|---|---|
| 追加前 | 3 行 |
| 追加 | **186 行** |
| 追加后 | 189 行 |
| 其中 `verified` | 16 |

路径：`D:\desktop\新量化策略\gpt数据保存\mt5_runs\run_manifest.jsonl`

## 产物

- `orphan_runs.csv`
- 本文件

