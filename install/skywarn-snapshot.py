#!/usr/bin/env python3
"""Explicit, version-guarded optional integration. Never execute SkywarnPlus."""
import argparse
import ast
import hashlib
import copy
import os
from pathlib import Path
import shutil
import tempfile

SUPPORTED = {
    'get_alerts': '750c01ce398cab0473c296417a89b6014686d1f7d67013111012b57c99b23a47',
    'main': 'f88ce86d309b644a1c1a60e10a130faf322b9b06abb43ea670de45c0c0f49f6d',
}
IMPORT = '\n# BlueNode weather observer v1 (optional, read-only)\ntry:\n    import bluenode_skywarn_snapshot as _bluenode_weather\nexcept Exception:\n    _bluenode_weather = None\n\n'
CALL = '    alerts = get_alerts(COUNTY_CODES)'
WRAPPED = '    alerts = (_bluenode_weather.collect(get_alerts, COUNTY_CODES, config, TMP_DIR, county_data)\n              if _bluenode_weather is not None else get_alerts(COUNTY_CODES))'
EXCEPT = '        except requests.exceptions.RequestException as e:'
NOTIFY = '            if _bluenode_weather is not None:\n                _bluenode_weather.zone_success()\n\n'


def fingerprint(node):
    node = copy.deepcopy(node)
    for child in ast.walk(node):
        if hasattr(child, 'type_params') and not child.type_params:
            del child.type_params  # Stable fingerprints across Python 3.11 and 3.12+.
    try:
        dumped = ast.dump(node, include_attributes=False, show_empty=True)
    except TypeError:  # Python <=3.12 always includes empty list fields.
        dumped = ast.dump(node, include_attributes=False)
    return hashlib.sha256(dumped.encode()).hexdigest()


def patch_source(source, supported=None):
    supported = SUPPORTED if supported is None else supported
    if '# BlueNode weather observer v1' in source:
        if source.count(IMPORT) != 1 or source.count(WRAPPED) != 1 or source.count(NOTIFY + EXCEPT) != 1:
            raise ValueError('Incomplete or modified observer patch')
        # Validate the reversible patch and original functions on every invocation.
        original = source.replace(IMPORT, '', 1).replace(WRAPPED, CALL, 1).replace(NOTIFY + EXCEPT, EXCEPT, 1)
        if patch_source(original, supported) != source:
            raise ValueError('Existing observer patch was modified')
        return source
    tree = ast.parse(source)
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for name, digest in supported.items():
        if name not in functions or fingerprint(functions[name]) != digest:
            raise ValueError('Unsupported SkywarnPlus function: ' + name + '; audit upstream update first')
    if source.count(CALL) != 1 or source.count(EXCEPT) != 1:
        raise ValueError('Ambiguous integration point')
    position = functions['get_alerts'].lineno - 1
    lines = source.splitlines(keepends=True)
    lines.insert(position, IMPORT)
    result = ''.join(lines).replace(CALL, WRAPPED).replace(EXCEPT, NOTIFY + EXCEPT)
    ast.parse(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skywarn-root', type=Path, default=Path('/usr/local/bin/SkywarnPlus'))
    parser.add_argument('--install', action='store_true', help='Apply after the default read-only check succeeds')
    args = parser.parse_args()
    target = args.skywarn_root / 'SkywarnPlus.py'
    if target.is_symlink() or not target.is_file():
        raise SystemExit('Expected a regular SkywarnPlus.py')
    original = target.read_text(encoding='utf-8-sig')
    patched = patch_source(original)
    if not args.install:
        print('PASS supported observer integration; no files changed')
        return
    if os.geteuid() != 0:
        raise SystemExit('Installation requires root')
    backup = target.with_name('SkywarnPlus.py.bluenode-before-' + hashlib.sha256(target.read_bytes()).hexdigest()[:16])
    if not backup.exists():
        shutil.copy2(target, backup)
    module = Path(__file__).resolve().parents[1] / 'core/skywarn_snapshot_exporter.py'
    for destination, data in [(args.skywarn_root / 'bluenode_skywarn_snapshot.py', module.read_bytes()),
                              (target, patched.encode('utf-8'))]:
        with tempfile.NamedTemporaryFile(dir=args.skywarn_root, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.chown(temporary, 0, 0)
        os.chmod(temporary, 0o755 if destination == target else 0o644)
        os.replace(temporary, destination)
    print('PASS observer installed; no SkywarnPlus execution or service restart performed')


if __name__ == '__main__':
    main()
