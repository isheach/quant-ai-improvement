import json, sys, tempfile, unittest
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from formal_engine import Account, Bar, InstrumentSpec, execute_signal_sequence, open_position, close_position, pnl, round_lot_down
from research_workflow import reserve, finish

class EngineeringSyntheticTest(unittest.TestCase):
    def setUp(self):
        lock=Path(__file__).resolve().parents[1]/'.engineering_run.lock'
        if lock.exists(): lock.rmdir()
    def bars(self):
        t=datetime(2023,1,1)
        return [Bar(t+timedelta(minutes=i),2000,2001,1999,2000,200,1999.9,2000.1) for i in range(4)]
    def test_fixed_quote_no_double_spread(self):
        result=execute_signal_sequence(self.bars(), {0:{'action':'open','side':1,'volume':0.01}, 1:{'action':'close','reason':'signal'}})
        self.assertEqual(len(result['legs']),1)
        self.assertAlmostEqual(result['legs'][0]['net'],-0.2,8)
        result=execute_signal_sequence(self.bars(), {0:{'action':'open','side':-1,'volume':0.01}, 1:{'action':'close','reason':'signal'}})
        self.assertAlmostEqual(result['legs'][0]['net'],-0.2,8)
    def test_volume_is_preserved_and_accounted(self):
        bars=self.bars(); spec=InstrumentSpec(); account=Account(); pos,_=open_position(account,bars[0],0,1,0.005,spec)
        self.assertIsNone(pos)
        pos,reason=open_position(account,bars[0],0,1,0.02,spec)
        self.assertEqual(reason,'accepted'); leg=close_position(account,pos,bars[1],1,'test',spec)
        self.assertEqual(leg['volume'],0.02); self.assertAlmostEqual(leg['gross'],-0.4,8)
    def test_grid_style_legs_sum_to_basket(self):
        bars=self.bars(); spec=InstrumentSpec(volume_min=0.005,volume_step=0.005); account=Account(); legs=[]
        for i in (0,1):
            pos,_=open_position(account,bars[i],i,1,0.005,spec)
            if pos: legs.append(close_position(account,pos,bars[2],2,'basket_close',spec))
        self.assertAlmostEqual(sum(x['net'] for x in legs),-0.2,8)
    def test_signal_executes_next_event(self):
        result=execute_signal_sequence(self.bars(), {0:{'action':'open','side':1,'volume':0.01}})
        self.assertEqual(result['decisions'][0]['execution_index'],1)
        self.assertEqual(result['legs'][0]['entry_i'],1)
    def test_gap_stop_fills_at_quote_event(self):
        bars=self.bars(); bars[2]=Bar(bars[2].t,2005,2010,2004,2008,200,2007.9,2008.1)
        result=execute_signal_sequence(bars,{0:{'action':'open','side':1,'volume':0.01,'stop':1995}})
        self.assertEqual(result['legs'][0]['reason'],'end')
        bars[2]=Bar(bars[2].t,1990,1991,1985,1988,200,1987.9,1988.1)
        result=execute_signal_sequence(bars,{0:{'action':'open','side':1,'volume':0.01,'stop':1995}})
        self.assertEqual(result['legs'][0]['reason'],'stop'); self.assertAlmostEqual(result['legs'][0]['exit'],1987.9,8)
    def test_workflow_reserve_complete_idempotent(self):
        root=Path(__file__).resolve().parents[1]; run_id='synthetic_workflow_test'
        target=root/'runs'/'engineering'/run_id
        if target.exists():
            import shutil; shutil.rmtree(target)
        state=reserve(run_id); self.assertEqual(state['status'],'RESERVED'); done=finish(run_id); self.assertEqual(done['status'],'COMPLETED')
        again=reserve(run_id); self.assertEqual(again['status'],'COMPLETED')
    def test_workflow_rejects_unknown_existing_state(self):
        root=Path(__file__).resolve().parents[1]; run_id='synthetic_unknown_test'; target=root/'runs'/'engineering'/run_id; target.mkdir(parents=True,exist_ok=True)
        try:
            with self.assertRaises(RuntimeError): reserve(run_id)
        finally:
            import shutil; shutil.rmtree(target)

if __name__=='__main__': unittest.main()

