const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const script = fs.readFileSync(path.join(root, 'install/remote-access.sh'), 'utf8');
const template = fs.readFileSync(path.join(root, 'install/remote-access/apache-vhost.conf.template'), 'utf8');
const example = fs.readFileSync(path.join(root, 'install/remote-access.conf.example'), 'utf8');
const docs = fs.readFileSync(path.join(root, 'docs/REMOTE_ACCESS.md'), 'utf8');
const installer = fs.readFileSync(path.join(root, 'install/install.sh'), 'utf8');
const funnelScript = fs.readFileSync(path.join(root, 'install/tailscale-funnel.sh'), 'utf8');
const funnelTemplate = fs.readFileSync(path.join(root, 'install/remote-access/apache-funnel-gateway.conf.template'), 'utf8');

assert.match(script, /BLUENODE_REMOTE_MODE:.*direct:enable/s);
assert.match(script, /apache2ctl[^\n]*configtest|\$APACHECTL configtest/);
assert.match(script, /activation failed; restoring previous Apache state/);
assert.match(script, /127\\\.0\\\.0\\\.1/);
assert.match(script, /evasive20_module/);
assert.match(template, /<Location "\/">[\s\S]*AuthType Basic[\s\S]*Require valid-user/);
assert.match(template, /ProxyPass \/ @BACKEND_URL@\//);
assert.match(template, /Strict-Transport-Security/);
assert.match(template, /<Location "\/allmon3">[\s\S]*Require all denied/);
assert.match(template, /<Location "\/server-status">[\s\S]*Require all denied/);
assert.doesNotMatch(template, /<VirtualHost[^>]*:80>/);
assert.match(example, /example\.invalid/);
assert.match(docs, /Never publish or forward TCP 8080/);
assert.match(docs, /every API\/control path/);
assert.match(installer, /install -m 0755[^\n]*remote-access\.sh/);
assert.match(installer, /install -m 0755[^\n]*tailscale-funnel\.sh/);
assert.match(funnelTemplate, /Listen 127\.0\.0\.1:@GATEWAY_PORT@/);
assert.match(funnelTemplate, /<Location "\/">[\s\S]*AuthType Basic[\s\S]*Require valid-user/);
assert.match(funnelTemplate, /ProxyPass \/ http:\/\/127\.0\.0\.1:@BACKEND_PORT@\//);
assert.match(funnelScript, /BLUENODE_FUNNEL_GATEWAY_PORT != 8080/);
assert.match(funnelScript, /\[\[ "\$unauth" == 401 \]\]/);
assert.match(funnelScript, /verify_credentials[\s\S]*tailscale funnel|verify_credentials[\s\S]*\$TAILSCALE funnel/);
assert.match(funnelScript, /--user "\$auth_user"/);
assert.doesNotMatch(funnelScript, /auth_password/);
assert.match(funnelScript, /funnel --bg --https=443 "http:\/\/127\.0\.0\.1:/);
assert.match(funnelScript, /funnel --https=443 off/);

const forbidden = [
  /N0CALL/i, /12345/, /192\.0\.2\.23/, /198\.51\.100\.16/
];
for (const pattern of forbidden) {
  for (const [name, content] of [['script', script], ['template', template], ['example', example], ['docs', docs]]) {
    assert.doesNotMatch(content, pattern, `${name} contains node-specific data`);
  }
}

for (const pattern of forbidden) {
  assert.doesNotMatch(funnelScript, pattern, 'Funnel script contains node-specific data');
  assert.doesNotMatch(funnelTemplate, pattern, 'Funnel template contains node-specific data');
}

console.log('PASS remote access framework tests');
