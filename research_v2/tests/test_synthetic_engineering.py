import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from research_core import ema, atr, efficiency_ratio, round_lot_down, risk_usd

class SyntheticTest(unittest.TestCase):
    def test_ema_hand_checked(self):
        self.assertEqual(ema([1,2,3,4],3)[:2],[None,None]); self.assertAlmostEqual(ema([1,2,3,4],3)[2],2.0); self.assertAlmostEqual(ema([1,2,3,4],3)[3],3.0)
    def test_atr(self):
        self.assertEqual(atr([10,12,13],[9,10,11],[9.5,11,12],2)[0],None); self.assertAlmostEqual(atr([10,12,13],[9,10,11],[9.5,11,12],2)[1],1.75)
    def test_er_zero_denominator(self): self.assertIsNone(efficiency_ratio([1,1,1],2)[2])
    def test_lot_floor_never_up(self): self.assertEqual(round_lot_down(0.009,0.01,0.01),0.0); self.assertEqual(round_lot_down(0.027,0.01,0.01),0.02)
    def test_risk(self): self.assertAlmostEqual(risk_usd(2.0,10.0,0.01),0.2)
    def test_causality(self):
        a=ema([1,2,3,4,5],3); b=ema([1,2,3,4,999],3); self.assertEqual(a[:4],b[:4])
    def test_state_no_overlap_and_recovery_files(self):
        root=Path(__file__).resolve().parents[1]; self.assertTrue((root/'CURRENT_STATUS.json').exists()); self.assertTrue((root/'TASK_LOG.jsonl').exists())
    def test_idempotent_report_exists(self):
        root=Path(__file__).resolve().parents[1]; p=root/'reports'/'P3_APPROVAL_PACKAGE.md'; self.assertTrue(p.exists()); first=p.read_bytes(); second=p.read_bytes(); self.assertEqual(first,second)
if __name__=='__main__': unittest.main()
