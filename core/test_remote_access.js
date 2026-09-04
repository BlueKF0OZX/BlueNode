const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const script = fs.readFileSync(path.join(root, 'install/remote-access.sh'), 'utf8');
const template = fs.readFileSync(path.join(root, 'install/remote-access/apache-vhost.conf.template'), 'utf8');
const example = fs.readFileSync(path.join(root, 'install/remote-access.conf.example'), 'utf8');
const docs = fs.readFileSync(path.join(root, 'docs/REMOTE_ACCESS.md'), 'utf8');
const installer = fs.readFileSync(path.join(root, 'install/install.sh'), 'utf8');

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

const forbidden = [
  /KF0OZX/i, /60873/, /192\.168\.8\.23/, /2\.90\.110\.16/
];
for (const pattern of forbidden) {
  for (const [name, content] of [['script', script], ['template', template], ['example', example], ['docs', docs]]) {
    assert.doesNotMatch(content, pattern, `${name} contains node-specific data`);
  }
}

console.log('PASS remote access framework tests');
