import concurrent.futures
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import favorites


class FavoritesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def change(self, revision=0, **change):
        return favorites.update(self.root, '12345', {'local_node': '12345', 'revision': revision, **change})

    def test_save_rename_remove_and_restart(self):
        self.assertEqual(favorites.read(self.root, '12345')[1]['favorites'], [])
        self.assertEqual(self.change(operation='save', item={'node':'23456','label':' First '})[0], 200)
        self.assertEqual(self.change(1, operation='save', item={'node':'23456','label':'Renamed'})[0], 200)
        # A fresh read from disk represents another browser or a restarted service.
        self.assertEqual(favorites.read(self.root, '12345')[1]['favorites'], [{'node':'23456','label':'Renamed'}])
        self.assertEqual(self.change(2, operation='remove', node='23456')[1]['favorites'], [])

    def test_competing_devices_cannot_overwrite_each_other(self):
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda node: self.change(operation='save', item={'node':node,'label':'Name'}), ['23456','34567']))
        self.assertEqual(sorted(status for status, _ in results), [200,409])
        self.assertEqual(len(favorites.read(self.root, '12345')[1]['favorites']), 1)

    def test_import_preserves_shared_names_and_does_not_duplicate(self):
        self.change(operation='save', item={'node':'23456','label':'Shared'})
        result = self.change(1, operation='import', items=[{'node':'23456','label':'Old'}, {'node':'34567','label':'New'}])
        self.assertEqual(result[1]['favorites'], [{'node':'23456','label':'Shared'}, {'node':'34567','label':'New'}])

    def test_invalid_requests_leave_file_unchanged(self):
        self.change(operation='save', item={'node':'23456','label':'Shared'})
        path = self.root / 'state/favorites.json'
        original = path.read_bytes()
        for item in ({'node':'12345','label':'Self'}, {'node':'../bad','label':''},
                     {'node':'23456','label':'x'*49}, {'node':'23456','label':'bad\nline'},
                     {'node':'23456','label':None}, {'node':'23456','label':'','extra':1}):
            self.assertEqual(self.change(1, operation='save', item=item)[0],400)
        for payload in (None, {}, {'local_node':'54321','revision':1,'operation':'remove','node':'23456'},
                        {'local_node':'12345','revision':True,'operation':'remove','node':'23456'}):
            self.assertEqual(favorites.update(self.root,'12345',payload)[0],400)
        self.assertEqual(path.read_bytes(), original)

    def test_capacity_is_atomic(self):
        items = [{'node':str(20000+i),'label':''} for i in range(20)]
        self.assertEqual(self.change(operation='import',items=items)[0],200)
        self.assertEqual(self.change(1,operation='save',item={'node':'34567','label':''})[0],400)
        self.assertEqual(len(favorites.read(self.root,'12345')[1]['favorites']),20)

    def test_corrupt_wrong_node_and_oversized_state_fail_closed(self):
        path = self.root / 'state/favorites.json'; path.parent.mkdir()
        for raw in ('{', 'x'*32769, json.dumps({'local_node':'54321','revision':1,'favorites':[]})):
            path.write_text(raw)
            self.assertEqual(favorites.read(self.root,'12345')[0],503)
            self.assertEqual(self.change(operation='remove',node='23456')[0],503)
            self.assertEqual(path.read_text(),raw)

    def test_failed_write_preserves_existing_state(self):
        self.change(operation='save',item={'node':'23456','label':'Original'})
        with patch.object(favorites,'atomic_json',side_effect=OSError('read only')):
            self.assertEqual(self.change(1,operation='remove',node='23456')[0],503)
        self.assertEqual(favorites.read(self.root,'12345')[1]['favorites'][0]['label'],'Original')
