"""
No built path may be a Windows reserved name (CON, PRN, AUX, NUL, COM1-9,
LPT1-9, any case, any extension): Windows can't check such a file or folder
out, so the repo wouldn't clone there. Covers every committed path and every
team slug any sport can build a page from (sports.WINDOWS_RESERVED).
"""
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import sports  # noqa: E402


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()

RESERVED = {'con', 'prn', 'aux', 'nul'} | {f'{p}{i}' for p in ('com', 'lpt') for i in range(1, 10)}


def reserved(segment):
    return segment.split('.')[0].strip().lower() in RESERVED


class WindowsPaths(unittest.TestCase):
    def test_the_list_matches_sports(self):
        self.assertEqual(sports.WINDOWS_RESERVED, RESERVED)

    def test_no_committed_path_segment_is_reserved(self):
        out = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True).stdout.decode()
        bad = [p for p in out.split('\0') if p and any(reserved(s) for s in p.split('/'))]
        self.assertEqual(bad, [])

    def test_no_built_folder_is_reserved(self):
        bad = []
        for d, dirs, files in os.walk(ROOT):
            dirs[:] = [x for x in dirs if x not in ('.git', 'node_modules')]
            bad += [os.path.relpath(os.path.join(d, x), ROOT) for x in dirs + files if reserved(x)]
        self.assertEqual(bad, [])

    def test_no_team_slug_is_reserved_in_any_sport(self):
        for sp in sports.SPORTS:
            path = os.path.join(ROOT, 'data_seed', 'teams', f"{sp['key']}.json")
            teams = json.loads(read(path))['teams'] if os.path.exists(path) else []
            for t in teams + [m['team'] for m in sports.moves(sp['key'])]:
                with self.subTest(sport=sp['key'], team=t['slug']):
                    self.assertFalse(reserved(t['slug']))
                    self.assertFalse(reserved(sports.team_slug(t.get('short') or t.get('name') or t['slug'])))

    def test_a_pro_code_that_is_reserved_gets_a_safe_slug(self):
        self.assertEqual(sports.pro_slug('wnba', 'CON'), 'conn')
        self.assertEqual(sports.pro_slug('nba', 'BOS'), 'bos')


if __name__ == '__main__':
    unittest.main()
