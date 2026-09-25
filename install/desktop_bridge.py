#!/usr/bin/env python3
"""Private SSH setup adapter. No HTTP endpoint, credentials, or radio commands.

The authenticated sudo operator supplies a release checkout. Installation runs
in a detached, root-owned job so losing the Windows connection cannot kill it.
Existing installations are read/verified only; updates retain the CLI workflow.
"""
import base64
import contextlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

import quickstart as q

JOBS = Path('/var/lib/bluenode-setup/jobs')
LOCK = '/run/bluenode-setup.lock'
PAYLOAD = ('core', 'web', 'install', 'config', 'systemd')


def decode(value):
    if len(value) > 8192:
        raise ValueError('Setup request is too large')
    request = json.loads(base64.b64decode(value, validate=True))
    if not isinstance(request, dict):
        raise ValueError('Invalid setup request')
    return request


def job_path(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{32}', value):
        raise ValueError('Invalid setup job')
    return JOBS / value


def save(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data))
    temporary.replace(path)


@contextlib.contextmanager
def lock():
    import fcntl
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield fd
    except BlockingIOError as error:
        raise ValueError('Another setup is running. Reconnect to check its progress.') from error
    finally:
        os.close(fd)


def station(config):
    # Never send the full configuration (which can contain optional secrets).
    host = config['web']['host']
    port = config['web']['port']
    if host != '127.0.0.1' and not q.trusted_address(host):
        raise ValueError('This custom dashboard listener needs the manual access guide.')
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('Unsupported dashboard port')
    return {'node': str(config['node']), 'callsign': config['callsign'], 'host': host, 'port': port,
            'welcome': (q.ROOT / 'web/welcome.html').is_file()}


def status(identifier):
    path = job_path(identifier)
    if not path.is_dir():
        raise ValueError('Setup job was not found')
    q.private_directory(path)
    value = json.loads((path / 'status.json').read_text())
    if value['state'] == 'running':
        try:
            pid_file = path / 'pid'
            os.kill(int(pid_file.read_text()) if pid_file.exists() else value['pid'], 0)
        except ProcessLookupError:
            value = {'state': 'failed', 'message': 'Setup was interrupted on the node. Check its private log before retrying.'}
    value['job'] = identifier
    value['log'] = str(path / 'install.log')
    return value


def active_job():
    pointer = JOBS / 'latest'
    if pointer.is_file():
        return status(pointer.read_text().strip())
    return None


def probe():
    previous = active_job()
    if previous and previous['state'] == 'running':
        return {'mode': 'running', **previous}
    q.preflight()
    if q.CONFIG.exists():
        config = json.loads(q.CONFIG.read_text())
        q.verify(config)
        return {'mode': 'existing', 'station': station(config)}
    q.fresh_guard()
    nodes = {node: call for node, call in q.discover_nodes().items()
             if 'RPT_' in q.run('/usr/sbin/asterisk', '-rx', 'rpt show variables ' + node)}
    if not nodes:
        raise ValueError('No working local AllStar nodes were found. Finish ASL3 setup first.')
    return {'mode': 'new', 'nodes': nodes, 'previous': previous}


def validated_config(request):
    if request.get('confirmed') is not True:
        raise ValueError('Installation must be confirmed in the setup assistant.')
    nodes = q.discover_nodes()
    node = request.get('node')
    if node not in nodes or 'RPT_' not in q.run('/usr/sbin/asterisk', '-rx', 'rpt show variables ' + node):
        raise ValueError('Choose a running local node.')
    example = json.loads((q.SOURCE / 'config/nodesmart.example.json').read_text())
    # This first desktop version deliberately offers private SSH access only.
    return q.build_config(example, node, request.get('callsign', '').upper(),
                          '127.0.0.1', request.get('port', 8080), nodes, [])


def copy_source(destination):
    for name in PAYLOAD:
        source = q.SOURCE / name
        if source.is_symlink() or not source.is_dir():
            raise ValueError('Incomplete release payload')
        for entry in source.rglob('*'):
            if entry.is_symlink() or (not entry.is_file() and not entry.is_dir()):
                raise ValueError('Unsupported file in release payload')
        shutil.copytree(source, destination / name)


def start(request):
    with lock() as fd:
        q.preflight()
        q.fresh_guard()
        config = validated_config(request)
        q.probe_port('127.0.0.1', config['web']['port'])
        q.private_directory(JOBS.parent)
        q.private_directory(JOBS)
        identifier = uuid.uuid4().hex
        job = job_path(identifier)
        job.mkdir(mode=0o700)
        copy_source(job / 'source')
        save(job / 'config.json', config)
        save(job / 'status.json', {'state': 'running', 'pid': os.getpid()})
        with (job / 'install.log').open('x') as log:
            child = subprocess.Popen([sys.executable, '-u', str(job / 'source/install/desktop_bridge.py'),
                                      'worker', identifier, str(fd)],
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True, pass_fds=(fd,))
        # Child inherits the held installer lock, with no gap for a second setup.
        # Only the child writes status after spawning (avoids overwriting success).
        (job / 'pid').write_text(str(child.pid))
        (JOBS / 'latest').write_text(identifier)
        return {'job': identifier, 'state': 'running'}


def worker(identifier, fd):
    job = job_path(identifier)
    save(job / 'status.json', {'state': 'running', 'pid': os.getpid()})
    try:
        config = json.loads((job / 'config.json').read_text())
        q.preflight()
        q.install(config)
        save(job / 'status.json', {'state': 'complete', 'station': station(config)})
    except BaseException as error:
        print('Setup failed:', error, flush=True)
        save(job / 'status.json', {'state': 'failed', 'message': str(error)})
    finally:
        os.close(fd)


def main():
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise ValueError('The setup assistant needs a node login with sudo access.')
    os.umask(0o077)
    os.environ['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
    if len(sys.argv) == 4 and sys.argv[1] == 'worker':
        worker(sys.argv[2], int(sys.argv[3]))
        return
    request = decode(sys.argv[1])
    action = request.get('action')
    if action == 'probe':
        result = probe()
    elif action == 'start':
        result = start(request)
    elif action == 'status':
        result = status(request.get('job'))
    else:
        raise ValueError('Unknown setup action')
    print(json.dumps({'ok': True, **result}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'ok': False, 'message': str(error)}))
        sys.exit(1)
