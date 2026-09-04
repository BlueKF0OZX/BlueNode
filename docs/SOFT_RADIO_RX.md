# Soft Radio Phase A: RX only

Soft Radio RX is optional and disabled by default. It lets a separately
authorized Remote Admin session listen to the operator's own App_Rpt node over
the existing HTTPS origin. Phase A has no microphone, PTT, DTMF, transmit
lease, transmit endpoint, or browser-controlled Asterisk operation.

## Media and security boundaries

The fixed media path is:

```text
App_Rpt node conference (Pm monitor mode)
  -> WebSocket/bluenode_soft_radio_rx/c(ulaw)f(json)d(in)
  -> ws://127.0.0.1:8767/asterisk-media
  -> BlueNode bounded RX broker
  -> authenticated same-origin /api/soft-radio/ws
  -> AudioWorklet -> browser audio output
```

In Asterisk's chan_websocket terminology, `d(in)` is from the external
application's perspective: Asterisk sends media to BlueNode and drops media
received from BlueNode. App_Rpt uses `Pm`, the monitor-only submode of phone
mode. The broker never writes media or control text to Asterisk. It closes a
browser that sends text or binary data. These are independent RX-only
enforcements.

The Asterisk-facing socket binds only to loopback, requires a generated Basic
credential, and accepts only the fixed `/asterisk-media` path and `media`
subprotocol. The browser never receives this credential. Browser admission
also requires all of the following:

- an unexpired Remote Admin session;
- the separately configured `soft_radio_rx` permission;
- same-origin HTTPS/WSS;
- a CSRF-protected ticket request; and
- a session-bound, one-time ticket that expires within 30 seconds.

Tickets and sessions are held in memory, never browser storage. Logout,
session expiry, configuration disablement, web-service failure, navigation,
and socket loss close listening. Audit records contain only action, timestamp,
and outcome, never tickets, credentials, URLs, or audio.
The ticket travels in WebSocket subprotocol negotiation rather than the URL,
so normal HTTP access logs do not capture it.

## Prepare without activating

Use the node number from the operator's untracked BlueNode configuration:

```sh
sudo NODESMART_USER=SERVICE_USER bash /opt/nodesmart/install/soft-radio-rx.sh prepare LOCAL_NODE
```

This creates `/etc/bluenode/soft-radio.json` disabled and stages a root-only,
randomly authenticated client stanza at
`/etc/bluenode/soft-radio-websocket-client.conf`. It does not modify or reload
Asterisk and does not start a media channel.

Enable Remote Admin through its existing procedure, then grant the separate
RX permission (this invalidates existing sessions):

```sh
sudo NODESMART_USER=SERVICE_USER bash /opt/nodesmart/install/remote-admin.sh grant-soft-radio-rx
```

## Activation gate

Activation requires installing the staged stanza into the local
`websocket_client.conf` and loading `res_websocket_client.so` and
`chan_websocket.so`. On an `autoload=no` ASL3 node this is an Asterisk
configuration/module operation. Validate the exact installed Asterisk build
and obtain operator approval before doing it; do not automate it as part of a
normal BlueNode deployment.

Only after those modules and the fixed stanza are active may the operator run:

```sh
sudo NODESMART_USER=SERVICE_USER bash /opt/nodesmart/install/soft-radio-rx.sh enable
```

The enable command refuses unless Remote Admin, `soft_radio_rx`, both modules,
and the fixed client stanza are present. It then enables the loopback broker
and creates only the fixed `ulaw`/`d(in)`/`Pm` monitor channel. No browser input
is used to form the command. The broker can invoke only a root-owned,
no-argument helper through an exact sudo rule; that helper independently
validates the external node and connection identifiers.

Disable immediately with:

```sh
sudo NODESMART_USER=SERVICE_USER bash /opt/nodesmart/install/soft-radio-rx.sh disable
sudo NODESMART_USER=SERVICE_USER bash /opt/nodesmart/install/remote-admin.sh revoke-soft-radio-rx
```

Disabling closes both media sides and leaves Asterisk, links, networking, and
the existing HTTPS gateway unchanged.

## Browser behavior and limitations

Modern Safari and Chromium browsers with AudioWorklet support can listen after
a user presses **Listen**, which satisfies mobile autoplay rules. The broker
forwards raw 8 kHz mono G.711 mu-law frames. The worklet decodes and resamples
them to the browser output rate, starts with a small jitter reserve, and drops
old audio rather than allowing delay to grow. Practical latency depends on the
browser and network and is expected to be a few hundred milliseconds.

Phase A permits one or more authorized listeners. Audio is not end-to-end
encrypted inside the host between Asterisk and the loopback broker; it is
HTTPS/WSS encrypted outside the host. RX availability depends on the installed
ASL3 chan_websocket and App_Rpt `Pm` behavior. There is deliberately no TX path.
