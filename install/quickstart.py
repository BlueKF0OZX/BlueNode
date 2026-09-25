#!/usr/bin/env python3
"""Interactive ASL3 onboarding. Never modifies or restarts Asterisk.

Run from a release checkout. Existing installs are detected and left untouched.
The established installer remains responsible for permissions and services.
"""
import argparse
import copy
import glob
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

SOURCE = Path(__file__).resolve().parents[1]
ROOT = Path('/opt/nodesmart')
CONFIG = ROOT / 'config/nodesmart.json'
LOG_ROOT = Path('/var/log/bluenode-setup')
BACKUP_ROOT = Path('/var/backups/bluenode')
MANAGED = [ROOT, Path('/etc/systemd/system/nodesmart.service'),
           Path('/etc/systemd/system/nodesmart-web.service'),
           Path('/etc/sudoers.d/nodesmart'), Path('/usr/local/sbin/bluenode-asterisk'),
           *(Path('/usr/local/bin') / name for name in ('dodropin', 'dodropoff', 'skywarnon', 'skywarnoff'))]
UNITS = ('nodesmart', 'nodesmart-web')
UPDATE_PATHS = MANAGED + [Path('/etc/bluenode'), Path('/etc/systemd/system/nodesmart-health.timer'),
                          Path('/etc/systemd/system/nodesmart-health.service')]


def run(*args, check=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30,
                            env={**os.environ, 'LC_ALL': 'C'})
    if check and result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(args) + '\n' + result.stderr[-1000:])
    return result.stdout.strip()


def radio_identity():
    return run('systemctl', 'show', 'asterisk', '-p', 'MainPID', '-p', 'ActiveEnterTimestampMonotonic')


def radio_files():
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in Path('/etc/asterisk').rglob('*') if path.is_file()}


def discover_nodes(path=Path('/etc/asterisk/rpt.conf')):
    """Read bounded local include files, never #exec or arbitrary external paths."""
    base = path.resolve().parent
    seen, nodes = set(), {}

    def read(file):
        file = file.resolve()
        if file in seen:
            return
        if not file.is_relative_to(base) or len(seen) >= 64:
            raise ValueError('Cannot safely read all rpt.conf includes; use manual setup.')
        seen.add(file)
        if file.stat().st_size > 1024 * 1024:
            raise ValueError('rpt.conf include is too large.')
        current = None
        for line in file.read_text().splitlines():
            include = re.match(r'^\s*#(?:try)?include\s+["<]?([^">;]+)', line)
            if include:
                pattern = include[1].strip()
                for child in sorted(glob.glob(str(file.parent / pattern))):
                    read(Path(child))
                continue
            section = re.match(r'^\s*\[([^]]+)\](.*)', line)
            if section:
                current = section[1] if re.fullmatch(r'[0-9]{1,10}', section[1]) and '!' not in section[2] else None
                if current:
                    nodes.setdefault(current, '')
            identity = re.match(r'^\s*idrecording\s*=\s*\|i([A-Za-z0-9/]+)\s*(?:;.*)?$', line)
            if current and identity:
                nodes[current] = identity[1].upper()
    read(path)
    return nodes


def local_addresses():
    interfaces = json.loads(run('ip', '-j', '-4', 'address', 'show'))
    return sorted({address['local'] for interface in interfaces for address in interface.get('addr_info', [])
                   if address.get('scope') == 'global' and trusted_address(address.get('local', ''))})


def trusted_address(value):
    try:
        address = ipaddress.IPv4Address(value)
        return any(address in ipaddress.ip_network(net) for net in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
    except ValueError:
        return False


def build_config(example, node, callsign, host, port, nodes, addresses):
    if node not in nodes:
        raise ValueError('Choose a local node detected in rpt.conf.')
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9/]{2,19}', callsign) or callsign == 'N0CALL':
        raise ValueError('Enter your station callsign, for example W1AW.')
    if host != '127.0.0.1' and host not in addresses:
        raise ValueError('Choose a detected trusted-network address or 127.0.0.1.')
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('Choose a port from 1024 to 65535.')
    result = copy.deepcopy(example)
    result.update(node=node, callsign=callsign, friendly_nodes={})
    result['web'] = {'host': host, 'port': port}
    result['recovery']['asterisk_enabled'] = False
    return result


def ask(prompt, default=''):
    value = input(prompt + (f' [{default}]' if default else '') + ': ').strip()
    return value or default


def choose_config(nodes, addresses):
    print('\n1. Your station')
    print('Detected local nodes: ' + ', '.join(nodes))
    node = ask('Node number', next(iter(nodes)) if len(nodes) == 1 else '')
    if node not in nodes:
        raise ValueError('That node was not detected. Run setup again and choose one from the list.')
    callsign = ask('Callsign', nodes[node]).upper()
    print('\n2. Dashboard access')
    print('Choose 127.0.0.1 for access through an SSH tunnel.')
    for address in addresses:
        print('Trusted home-network option: ' + address)
    print('Home-network access allows devices on that network to view and control your node.')
    print('Use it only on a network you trust. Internet access needs separate HTTPS/authentication setup.')
    host = ask('Dashboard address', '127.0.0.1')
    if host != '127.0.0.1' and ask('Is this a trusted private network? Type YES', '') != 'YES':
        raise ValueError('Network access was not confirmed; nothing was installed.')
    port = int(ask('Dashboard port', '8080'))
    return build_config(json.loads((SOURCE / 'config/nodesmart.example.json').read_text()),
                        node, callsign, host, port, nodes, addresses)


def probe_port(host, port):
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((host, port))
        except OSError as error:
            raise ValueError(f'{host}:{port} is unavailable. Choose another port or check the address.') from error


def verify(config, timeout=25):
    host, port = config['web']['host'], config['web']['port']
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    last = 'Waiting for first observation'
    while time.monotonic() < deadline:
        try:
            for unit in UNITS:
                if run('systemctl', 'is-active', unit) != 'active':
                    raise ValueError(unit + ' is not active')
            base = f'http://{host}:{port}'
            with opener.open(base + '/web/', timeout=3) as response:
                if b'BlueNode' not in response.read(2_000_000):
                    raise ValueError('Dashboard response does not identify BlueNode')
            with opener.open(base + '/state/system.json', timeout=3) as response:
                state = json.load(response)
            if str(state.get('node')) != config['node']:
                raise ValueError('Waiting for the configured local node observation')
            if state.get('asterisk_evidence', {}).get('node', {}).get('status') != 'available':
                raise ValueError('Waiting for a successful App_Rpt observation')
            if time.time() - (ROOT / 'state/system.json').stat().st_mtime > 15:
                raise ValueError('Station observations are stale')
            return
        except (OSError, ValueError, RuntimeError) as error:
            last = str(error)
            time.sleep(1)
    raise RuntimeError('BlueNode did not pass its startup check: ' + last)


def show_access(config):
    host, port = config['web']['host'], config['web']['port']
    print(f'\nOpen your dashboard: http://{host}:{port}/web/')
    if (ROOT / 'web/welcome.html').is_file():
        print(f'First visit? Start here: http://{host}:{port}/web/welcome.html')
    if host == '127.0.0.1':
        print('From another computer, first open an SSH tunnel:')
        print(f'  ssh -N -L {port}:127.0.0.1:{port} YOUR_LOGIN@YOUR_NODE_IP')
        print('Keep that terminal open, then use the dashboard link above.')
    print('Bookmark the dashboard. BlueNode starts automatically after reboot.')
    print('Weather, remote access, and automatic recovery can be set up later.')
    print('Need help? Use Troubleshooting Report in the dashboard, or docs/GET_STARTED.md.')


def fresh_guard():
    for path in MANAGED + [Path('/etc/bluenode'), Path('/etc/systemd/system/nodesmart-health.timer'),
                           Path('/etc/systemd/system/nodesmart-health.service')]:
        if path.exists() or path.is_symlink():
            raise ValueError(f'Existing installation or helper found: {path}. Nothing changed. See docs/UPGRADE.md.')
    for unit in UNITS:
        if run('systemctl', 'show', unit, '-p', 'LoadState', '--value') != 'not-found':
            raise ValueError('An existing BlueNode service was found. Use the upgrade guide.')


def preflight():
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise ValueError('Run with sudo on your ASL3 node, not on your Windows/Mac computer.')
    if not Path('/run/systemd/system').is_dir():
        raise ValueError('This node needs systemd.')
    os_info = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if os_info.get('ID', '').strip('"') != 'debian' or os_info.get('VERSION_ID', '').strip('"') != '12':
        raise ValueError('Guided setup currently supports Debian 12 ASL3. See docs/INSTALL.md for other platforms.')
    for command in ('python3', 'ip', 'ping', 'sudo', 'visudo', 'systemctl', 'asterisk', 'useradd', 'getent'):
        if not shutil.which(command):
            raise ValueError('Missing prerequisite: ' + command + '. Run the download/setup command in the README.')
    run('systemctl', 'is-active', '--quiet', 'asterisk')
    modules = run('/usr/sbin/asterisk', '-rx', 'module show like app_rpt.so')
    if 'app_rpt.so' not in modules or 'Running' not in modules:
        raise ValueError('AllStar App_Rpt is not running. Finish ASL3 setup first.')


def install(config):
    """Fresh-only transaction. Collision refusal makes cleanup narrowly owned."""
    import pwd
    fresh_guard()
    probe_port(config['web']['host'], config['web']['port'])
    before, files_before = radio_identity(), radio_files()
    try:
        pwd.getpwnam('bluenode')
    except KeyError:
        pass
    else:
        raise ValueError('The bluenode account already exists. Use the manual installation guide to preserve it.')
    log_dir = LOG_ROOT
    log_dir.mkdir(mode=0o700, exist_ok=True)
    if log_dir.is_symlink() or log_dir.stat().st_uid != 0 or log_dir.stat().st_mode & 0o077:
        raise ValueError('Unsafe setup log directory')
    descriptor, name = tempfile.mkstemp(prefix='install-', suffix='.log', dir=log_dir)
    os.close(descriptor)
    log_path = Path(name)
    # No commands run until all answers have been confirmed by the operator.
    subprocess.run(['useradd', '--system', '--user-group', '--home-dir', str(ROOT),
                    '--no-create-home', '--shell', '/usr/sbin/nologin', 'bluenode'], check=True)
    account = pwd.getpwnam('bluenode')
    try:
        ROOT.mkdir(mode=0o750)
        CONFIG.parent.mkdir(mode=0o750)
        with CONFIG.open('x') as handle:
            json.dump(config, handle, indent=2)
            handle.write('\n')
        os.chown(ROOT, 0, account.pw_gid)
        os.chown(CONFIG.parent, 0, account.pw_gid)
        os.chown(CONFIG, 0, account.pw_gid)
        CONFIG.chmod(0o640)
        with log_path.open('w') as log:
            result = subprocess.run(['bash', str(SOURCE / 'install/install.sh')],
                                    env={**os.environ, 'NODESMART_USER': 'bluenode'},
                                    stdout=log, stderr=subprocess.STDOUT, timeout=180)
        if result.returncode:
            raise RuntimeError('Installation failed. Details: ' + str(log_path))
        verify(config)
        if radio_identity() != before or radio_files() != files_before:
            raise RuntimeError('Asterisk changed during setup; inspect the node before proceeding.')
    except BaseException:
        # All these paths were absent at entry. Never touch Asterisk or operator files.
        subprocess.run(['systemctl', 'disable', '--now', *UNITS], capture_output=True, timeout=30)
        for path in MANAGED:
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
        subprocess.run(['systemctl', 'daemon-reload'], capture_output=True, timeout=30)
        subprocess.run(['userdel', 'bluenode'], capture_output=True, timeout=30)
        print('Incomplete BlueNode installation removed. Setup log: ' + str(log_path))
        raise
    print('\nBlueNode is ready. Dashboard and station checks passed.')
    print('Asterisk process and configuration are unchanged. Setup log: ' + str(log_path))
    show_access(config)


def private_directory(path):
    if path.is_symlink():
        raise ValueError('Unsafe backup directory')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_uid != 0 or path.stat().st_mode & 0o077:
        raise ValueError('Backup directory must be owned by root and private')


def snapshot(destination):
    """Called only with BlueNode stopped; preserve ownership, modes and symlinks."""
    present = []
    for index, path in enumerate(UPDATE_PATHS):
        if path.exists() or path.is_symlink():
            run('cp', '-a', '--', str(path), str(destination / str(index)))
            present.append(index)
    (destination / 'manifest.json').write_text(json.dumps({'paths': [str(p) for p in UPDATE_PATHS], 'present': present}))


def check_backup_space(parent):
    size = 0
    for root in UPDATE_PATHS:
        if root.is_symlink():
            continue
        if root.is_file():
            size += root.stat().st_size
        elif root.is_dir():
            for directory, _, files in os.walk(root, followlinks=False):
                for name in files:
                    path = Path(directory) / name
                    if not path.is_symlink():
                        size += path.stat().st_size
    if shutil.disk_usage(parent).free < size * 2 + 64 * 1024 * 1024:
        raise ValueError('Not enough disk space for a private backup and update. Free space before retrying.')


def restore_snapshot(destination):
    private_directory(destination)
    manifest = json.loads((destination / 'manifest.json').read_text())
    if manifest.get('paths') != [str(p) for p in UPDATE_PATHS]:
        raise ValueError('Backup is not compatible with this setup version')
    present = manifest.get('present')
    if not isinstance(present, list) or any(type(i) is not int or not 0 <= i < len(UPDATE_PATHS) for i in present):
        raise ValueError('Backup manifest is invalid')
    for i in present:
        if not (destination / str(i)).exists() and not (destination / str(i)).is_symlink():
            raise ValueError('Backup is incomplete')
    for index, path in enumerate(UPDATE_PATHS):
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        if index in present:
            run('cp', '-a', '--', str(destination / str(index)), str(path))
    run('systemctl', 'daemon-reload')


def rollback(destination):
    parent = BACKUP_ROOT.resolve()
    if destination.is_symlink() or destination.resolve().parent != parent or not destination.name.startswith('before-update-'):
        raise ValueError('Choose a before-update backup directly inside /var/backups/bluenode.')
    if not destination.is_dir():
        raise ValueError('That backup directory does not exist.')
    private_directory(destination)
    manifest = json.loads((destination / 'manifest.json').read_text())
    if manifest.get('paths') != [str(p) for p in UPDATE_PATHS]:
        raise ValueError('Incompatible backup; use its matching installer version.')
    if any(not (destination / str(i)).exists() and not (destination / str(i)).is_symlink()
           for i in manifest.get('present', [])):
        raise ValueError('Backup is incomplete')
    if ask('Restore saved settings and history from this backup? Type YES') != 'YES':
        return
    check_backup_space(parent)
    before, files_before = radio_identity(), radio_files()
    # Preserve the current files as well, including post-update history.
    current = Path(tempfile.mkdtemp(prefix='before-restore-', dir=parent))
    run('systemctl', 'stop', *UNITS)
    try:
        snapshot(current)
    except BaseException:
        run('systemctl', 'start', *UNITS)
        raise
    try:
        restore_snapshot(destination)
        run('systemctl', 'start', *UNITS)
        config = json.loads(CONFIG.read_text())
        verify(config)
        if radio_identity() != before or radio_files() != files_before:
            raise RuntimeError('Asterisk changed during restoration')
    except BaseException:
        run('systemctl', 'stop', *UNITS)
        restore_snapshot(current)
        run('systemctl', 'start', *UNITS)
        raise
    print('Backup restored and checked. Pre-restore files saved privately at ' + str(current))
    show_access(config)


def update(config):
    """Back up a supported working install, retain its identity and restore on failure."""
    if ROOT.is_symlink() or ROOT.resolve() == SOURCE.resolve():
        raise ValueError('Run updates from a separate release checkout; installation directory must not be a symlink.')
    # Keep this first-time guided updater conservative around legacy/custom services.
    for unit in UNITS:
        if run('systemctl', 'is-enabled', unit) != 'enabled':
            raise ValueError('Guided updates require both BlueNode services enabled. Use docs/UPGRADE.md.')
    for unit in ('nodesmart-health.timer', 'nodesmart-health.service'):
        if run('systemctl', 'show', unit, '-p', 'LoadState', '--value') != 'not-found':
            raise ValueError('Legacy health service detected. Follow docs/UPGRADE.md for migration.')
    service_user = run('systemctl', 'show', 'nodesmart.service', '-p', 'User', '--value')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*', service_user) or service_user == 'root':
        raise ValueError('Unsupported existing service identity')
    if run('systemctl', 'show', 'nodesmart-web.service', '-p', 'User', '--value') != service_user:
        raise ValueError('Service identities differ. Follow docs/UPGRADE.md.')
    if config.get('recovery', {}).get('asterisk_enabled') is not False:
        raise ValueError('Turn off automatic recovery before a guided update, then retry.')
    verify(config)
    before, files_before = radio_identity(), radio_files()
    config_before = CONFIG.read_bytes()
    parent = BACKUP_ROOT
    private_directory(parent)
    check_backup_space(parent)
    destination = Path(tempfile.mkdtemp(prefix='before-update-', dir=parent))
    print('Backup: ' + str(destination))
    run('systemctl', 'stop', *UNITS)
    complete = False
    try:
        snapshot(destination)
        complete = True
        with (destination / 'update.log').open('x') as log:
            result = subprocess.run(['bash', str(SOURCE / 'install/install.sh')],
                                    env={**os.environ, 'NODESMART_USER': service_user},
                                    stdout=log, stderr=subprocess.STDOUT, timeout=180)
        if result.returncode:
            raise RuntimeError('Installer failed')
        if CONFIG.read_bytes() != config_before:
            raise RuntimeError('Existing settings changed')
        verify(config)
        if radio_identity() != before or radio_files() != files_before:
            raise RuntimeError('Asterisk changed during the update')
    except BaseException:
        if complete:
            run('systemctl', 'stop', *UNITS)
            restore_snapshot(destination)
        run('systemctl', 'start', *UNITS)
        verify(config)
        print('Previous installation restored and checked. Details: ' + str(destination))
        raise
    print('Update verified. Your settings and radio configuration were preserved.')
    print('Keep this private backup for recovery: ' + str(destination))
    show_access(config)


def main():
    parser = argparse.ArgumentParser(description='Guided BlueNode setup for an existing ASL3 node')
    parser.add_argument('--check', action='store_true', help='Check an existing installation without changes')
    parser.add_argument('--update', action='store_true', help='Back up and update an existing installation from this checkout')
    parser.add_argument('--restore', type=Path, help='Restore a private before-update backup (asks for confirmation)')
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise ValueError('Run with sudo on your ASL3 node.')
    os.umask(0o077)
    os.environ['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
    import fcntl
    # Serialize quickstart instances; refuse symlink lock files.
    fd = os.open('/run/bluenode-setup.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w'):
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        preflight()
        if args.restore:
            if not sys.stdin.isatty():
                raise ValueError('Restoration needs an interactive terminal.')
            rollback(args.restore)
            return
        if CONFIG.exists():
            config = json.loads(CONFIG.read_text())
            if args.update:
                if not sys.stdin.isatty():
                    raise ValueError('Updates need an interactive terminal.')
                print('Update BlueNode from this checkout? Existing BlueNode code will be replaced.')
                print('Settings/history are backed up. The radio stays running; the dashboard pauses briefly.')
                if ask('Back up and update now? Type YES') == 'YES':
                    update(config)
                return
            print('BlueNode is already installed. Your settings have not been changed.')
            verify(config)
            show_access(config)
            print('For updates and rollback: https://github.com/BlueKF0OZX/BlueNode/blob/main/docs/UPGRADE.md')
            return
        if args.check:
            raise ValueError('BlueNode has not been installed yet.')
        if args.update:
            raise ValueError('No existing installation to update. Run setup without --update.')
        fresh_guard()
        nodes = discover_nodes()
        nodes = {node: call for node, call in nodes.items()
                 if 'RPT_' in run('/usr/sbin/asterisk', '-rx', 'rpt show variables ' + node)}
        if not nodes:
            raise ValueError('No running local AllStar nodes were found. Finish ASL3 setup first.')
        if not sys.stdin.isatty():
            raise ValueError('Setup needs an interactive terminal. Run the README command over SSH.')
        config = choose_config(nodes, local_addresses())
        print(f"\nInstall BlueNode for {config['callsign']}, node {config['node']}?")
        print(f"Dashboard: http://{config['web']['host']}:{config['web']['port']}/web/")
        print('Automatic recovery stays off. Your existing radio settings will be preserved.')
        if ask('Install now? Type YES') != 'YES':
            print('Cancelled. Nothing was installed.')
            return
        install(config)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit('Setup stopped: ' + str(error))
    except (EOFError, KeyboardInterrupt):
        sys.exit('\nSetup cancelled.')
