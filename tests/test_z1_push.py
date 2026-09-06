"""Replay actual transient-completion ordering through the coordinator handler."""
import ast
import asyncio
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/roborock_z1_monitor'
spec = importlib.util.spec_from_file_location('push_cycle',ROOT/'cycle.py')
cycle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cycle)
tree = ast.parse((ROOT/'__init__.py').read_text(encoding='utf-8'))
tree.body = [n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Z1Coordinator']
ns = {'DataUpdateCoordinator':object,'FIELDS':{203:'status',218:'washing_left',220:'error'},'advance':cycle.advance}
exec(compile(tree,'coordinator','exec'),ns)


class PushTests(unittest.IsolatedAsyncioTestCase):
    def coordinator(self):
        c=object.__new__(ns['Z1Coordinator'])
        c.cycle_lock=asyncio.Lock();c.push_cache={};c.cycles={};c.preferences={}
        c.save=AsyncMock();c.notify=Mock()
        return c

    async def test_real_five_second_signal_is_delivered_once(self):
        c=self.coordinator()
        for now,data in [(0,{203:6,218:6,220:0}),(60,{218:5}),(120,{203:1}),
                         (120.055,{203:10}),(125,{203:1}),(180,{203:1,218:1,220:0})]:
            await c.process_push('washer',data,now)
        c.notify.assert_called_once()
        self.assertTrue(c.save.await_count)

    async def test_dryer_cooling_then_complete(self):
        c=self.coordinator()
        for now,data in [(0,{203:7,218:10,220:0}),(60,{218:9}),(120,{203:8,218:3}),
                         (150,{203:7,218:1}),(160,{203:10,218:10}),(180,{203:10,218:10,220:0})]:
            await c.process_push('dryer',data,now)
        c.notify.assert_called_once()

    async def test_cancel_fault_stale_and_disabled_do_not_notify(self):
        for case in ('cancel','fault','stale','disabled'):
            c=self.coordinator()
            await c.process_push('washer',{203:6,218:6,220:0},0)
            await c.process_push('washer',{218:5},60)
            if case=='cancel':
                await c.process_push('washer',{203:1},120)
                await c.process_push('washer',{203:1},130)
            elif case=='fault':
                await c.process_push('washer',{220:3},119)
                await c.process_push('washer',{203:10},120)
            elif case=='stale':
                await c.process_push('washer',{203:10},300)
            else:
                c.preferences['washer']=False
                await c.process_push('washer',{203:10},120)
            c.notify.assert_not_called()


if __name__=='__main__':
    unittest.main()
