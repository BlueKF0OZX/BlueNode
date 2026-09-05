#!/usr/bin/env python3
"""Audit an operator-supplied upstream source without executing its module/main."""
import ast
from collections import OrderedDict
from datetime import datetime, timezone
import fnmatch
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'core'))
import skywarn_snapshot_exporter as exporter


def main():
    source = Path(sys.argv[1]).read_text(encoding='utf-8-sig')
    spec = importlib.util.spec_from_file_location('patcher', ROOT / 'install/skywarn-snapshot.py')
    patcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(patcher)
    patched = patcher.patch_source(source)
    assert patcher.patch_source(patched) == patched
    for failures in [set(), {0}, {1}]:
        with tempfile.TemporaryDirectory() as directory:
            stored = {'last_alerts': [['Flood Warning', [{'county_code':'XXC001', 'severity':4,
                'description':'Cached fixture', 'end_time_utc':'2099-01-01T00:00:00Z'}]]]}
            path = Path(directory) / 'data.json'; path.write_text(json.dumps(stored))
            results = []
            for text in [source, patched]:
                calls = []
                def get(url):
                    calls.append(url)
                    if len(calls)-1 in failures:
                        raise OSError('Synthetic upstream failure')
                    properties = {'onset':'2000-01-01T00:00:00Z', 'ends':'2099-01-01T00:00:00Z',
                                  'event':'Tornado Warning', 'severity':'Extreme', 'description':'Current fixture'}
                    return SimpleNamespace(raise_for_status=lambda:None, json=lambda:{'features':[{'properties':properties}]})
                scope = dict(OrderedDict=OrderedDict, datetime=datetime, timezone=timezone,
                    config={}, GLOBAL_BLOCKED_EVENTS=[], MAX_ALERTS=99, LOGGER=Mock(),
                    requests=SimpleNamespace(get=get, exceptions=SimpleNamespace(RequestException=OSError)),
                    parser=SimpleNamespace(isoparse=datetime.fromisoformat, parse=datetime.fromisoformat),
                    fnmatch=fnmatch, os=os, json=json, DATA_FILE=str(path), _bluenode_weather=exporter)
                node = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name=='get_alerts')
                exec(compile(ast.Module(body=[node], type_ignores=[]), '<isolated get_alerts>', 'exec'), scope)
                operation = scope['get_alerts']
                result = operation(['XXC001','XXC002']) if text == source else exporter.collect(operation, ['XXC001','XXC002'], {}, directory)
                results.append((result, calls))
            assert results[0] == results[1], 'Upstream return value or request sequence changed'
            snapshot = json.loads((Path(directory)/'bluenode-weather.json').read_text())
            assert snapshot['collection_status'] == ('success' if not failures else 'failure' if 0 in failures else 'partial')
            assert snapshot['alerts'] == json.loads(json.dumps(list(results[1][0].items())))
    print('PASS actual upstream: guarded patch, idempotency, unchanged requests/alerts, complete/partial/failure export; no main/radio execution')


if __name__ == '__main__':
    main()
