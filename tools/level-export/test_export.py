"""Regression tests for Tiled-to-runtime conversion and strict layer transforms.
Run: python -m unittest discover -s tools/level-export -p 'test_*.py' -v
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
sys.path.insert(0,str(HERE))
from export import convert, LevelError


class LevelExportRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=json.loads((ROOT/'levels-src/L003.tmj').read_text(encoding='utf8'))

    def run_source(self,src):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'modified.tmj'
            f.write_text(json.dumps(src),encoding='utf8')
            return convert(f)

    def layer(self,src,name):
        return next(x for x in src['layers'] if x['name']==name)

    def test_00_unmodified_level_is_accepted(self):
        result=self.run_source(copy.deepcopy(self.base))
        self.assertEqual(result['id'],'L003')
        self.assertEqual(len(result['grid']['rows']),160)

    def test_01_explicit_zero_offsets_are_accepted(self):
        source=copy.deepcopy(self.base)
        for name in ('bricks','markers'):
            self.layer(source,name).update(offsetx=0,offsety=0.0,x=0,y=0,parallaxx=1,parallaxy=1.0)
        self.assertEqual(self.run_source(source)['id'],'L003')

    def test_02_bricks_offsetx_offsety_8_rejected(self):
        for attr in ('offsetx','offsety'):
            with self.subTest(attr=attr):
                source=copy.deepcopy(self.base)
                self.layer(source,'bricks')[attr]=8
                with self.assertRaisesRegex(LevelError,rf'layer bricks.*{attr}=8'):
                    self.run_source(source)

    def test_03_markers_offsetx_offsety_8_rejected(self):
        for attr in ('offsetx','offsety'):
            with self.subTest(attr=attr):
                source=copy.deepcopy(self.base)
                self.layer(source,'markers')[attr]=8
                with self.assertRaisesRegex(LevelError,rf'layer markers.*{attr}=8'):
                    self.run_source(source)

    def test_04_negative_offsets_are_rejected(self):
        source=copy.deepcopy(self.base)
        self.layer(source,'markers')['offsetx']=-8
        with self.assertRaisesRegex(LevelError,'offsetx=-8'):
            self.run_source(source)

    def test_05_tilelayer_grid_shifts_are_rejected(self):
        for attr in ('x','y'):
            with self.subTest(attr=attr):
                source=copy.deepcopy(self.base)
                self.layer(source,'bricks')[attr]=1
                with self.assertRaisesRegex(LevelError,rf'layer bricks.*{attr}=1'):
                    self.run_source(source)

    def test_06_parallax_and_groups_are_rejected(self):
        source=copy.deepcopy(self.base)
        self.layer(source,'markers')['parallaxx']=1.2
        with self.assertRaisesRegex(LevelError,r'parallaxx=1.2'):
            self.run_source(source)
        source=copy.deepcopy(self.base)
        source['layers'].append({'type':'group','name':'nested','layers':[]})
        with self.assertRaisesRegex(LevelError,'group layers unsupported'):
            self.run_source(source)

    def test_07_cli_rejects_offset_without_clobbering_output(self):
        source=copy.deepcopy(self.base)
        self.layer(source,'markers')['offsety']=8
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); inp=p/'broken.tmj';out=p/'output.json'
            inp.write_text(json.dumps(source),encoding='utf8')
            out.write_text('UNCHANGED',encoding='utf8')
            r=subprocess.run([sys.executable,str(HERE/'export.py'), '--input',str(inp), '--output',str(out)],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertIn('markers',r.stderr)
            self.assertIn('offsety=8',r.stderr)
            self.assertEqual(out.read_text(),'UNCHANGED')

    def test_08_all_30_unshifted_sources_equal_export(self):
        for n in range(1,31):
            code=f'L{n:03d}'
            with self.subTest(level=code):
                actual=convert(ROOT/f'levels-src/{code}.tmj')
                expected=json.loads((ROOT/f'assets/levels/{code}.json').read_text(encoding='utf8'))
                self.assertEqual(actual,expected)

    def test_09_tilelayer_dimensions_reject_same_cell_count(self):
        # Each pair keeps data length 15,360 unchanged; dimension metadata
        # must not be discarded and reinterpreted as a 96x160 layer.
        for w, h in ((48, 320), (160, 96), (96, 159)):
            with self.subTest(width=w, height=h):
                source=copy.deepcopy(self.base)
                self.layer(source,'bricks').update(width=w,height=h)
                with self.assertRaisesRegex(LevelError,rf'layer bricks must be 96x160; got {w}x{h}'):
                    self.run_source(source)

    def test_10_missing_or_noninteger_tilelayer_dimensions_rejected(self):
        for field, value in (("width", None), ("width", 96.0), ("height", True),
                             ("height", "160")):
            with self.subTest(field=field, value=value):
                source=copy.deepcopy(self.base)
                self.layer(source,'bricks')[field]=value
                with self.assertRaisesRegex(LevelError,'layer bricks must be 96x160'):
                    self.run_source(source)

    def test_11_cli_rejects_mismatched_dimensions_without_clobbering_output(self):
        source=copy.deepcopy(self.base)
        self.layer(source,'bricks').update(width=48, height=320)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); inp=p/'bad_dimensions.tmj';out=p/'output.json'
            inp.write_text(json.dumps(source),encoding='utf8')
            out.write_text('PRESERVE_EXISTING_OUTPUT',encoding='utf8')
            r=subprocess.run([sys.executable,str(HERE/'export.py'), '--input',str(inp), '--output',str(out)],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertIn('layer bricks must be 96x160',r.stderr)
            self.assertIn('48x320',r.stderr)
            self.assertEqual(out.read_text(),'PRESERVE_EXISTING_OUTPUT')


if __name__=='__main__':unittest.main()
