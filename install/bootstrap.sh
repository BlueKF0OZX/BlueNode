#!/bin/bash
# Download a named BlueNode release; all questions use the terminal, not stdin.
set -Eeuo pipefail
umask 077
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
VERSION=v0.1.2-alpha.1
[[ $# -eq 0 || ( $# -eq 1 && "$1" == --update ) ]] || { echo 'Supported option: --update'; exit 1; }
[[ $EUID -eq 0 ]] || { echo 'Run this command with sudo.' >&2; exit 1; }
[[ -r /dev/tty ]] || { echo 'Open an interactive SSH terminal and try again.' >&2; exit 1; }
[[ -x /usr/sbin/asterisk && -d /run/systemd/system ]] || {
  echo 'BlueNode needs an existing working AllStarLink 3 node. Install ASL3 first.' >&2; exit 1;
}
echo "BlueNode $VERSION guided setup"
echo 'This installs missing download/setup tools, then asks about your station.'
read -r -p 'Continue? [y/N] ' answer </dev/tty
[[ "$answer" == [yY] ]] || exit 0
missing=()
for entry in 'git:git' 'python3:python3' 'curl:curl' 'sudo:sudo' 'ip:iproute2' 'ping:iputils-ping'; do
  command -v "${entry%%:*}" >/dev/null || missing+=("${entry#*:}")
done
if (( ${#missing[@]} )); then
  apt-get update
  apt-get install --no-install-recommends -y "${missing[@]}" ca-certificates
fi
work=$(mktemp -d /tmp/bluenode-setup.XXXXXXXX)
trap 'rm -rf -- "$work"' EXIT
git clone --quiet --depth 1 --branch "$VERSION" https://github.com/BlueKF0OZX/BlueNode.git "$work/source"
python3 "$work/source/install/quickstart.py" "$@" </dev/tty
