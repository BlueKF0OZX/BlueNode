"""Build the installed, script-free guide from its GitHub Markdown source."""
from pathlib import Path
import html
import re

ROOT = Path(__file__).resolve().parents[1]


def inline(text):
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html.escape(text))


def build():
    source = (ROOT / 'docs/DASHBOARD_GUIDE.md').read_text(encoding='utf-8')
    contents, body = [], []
    for block in source.strip().split('\n\n'):
        if block.startswith('# '):
            body.append('<h1>' + inline(block[2:]) + '</h1>')
        elif block.startswith('## '):
            title = block[3:]
            anchor = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
            contents.append(f'<li><a href="#{anchor}">{html.escape(title)}</a></li>')
            body.append(f'<h2 id="{anchor}">{inline(title)}</h2>')
        elif block.startswith('- '):
            body.append('<ul>' + ''.join('<li>' + inline(line[2:]) + '</li>' for line in block.splitlines()) + '</ul>')
        elif re.match(r'^1\. ', block):
            body.append('<ol>' + ''.join('<li>' + inline(re.sub(r'^\d+\. ', '', line)) + '</li>' for line in block.splitlines()) + '</ol>')
        else:
            body.append('<p>' + inline(block.replace('\n', ' ')) + '</p>')
    page = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard guide · BlueNode</title><style>
:root{color-scheme:dark;font:17px/1.65 system-ui,sans-serif;background:#101a2a;color:#eaf2ff}
*{box-sizing:border-box}body{margin:0}main{max-width:900px;margin:auto;padding:32px 24px 70px}
a{color:#9acaff}a:focus-visible{outline:3px solid #fff;outline-offset:4px}
h1{font-size:clamp(2rem,6vw,3rem);line-height:1.15}h2{font-size:1.4rem;border-top:1px solid #344960;padding-top:28px;margin-top:36px;scroll-margin-top:20px}
p,li{color:#c2cfe1}strong{color:#fff}li{margin:10px 0}ul,ol{padding-left:24px}
nav{padding:18px 24px;background:#172438;border:1px solid #344960;border-radius:12px}
nav ul{columns:2;column-gap:32px}nav li{break-inside:avoid;margin:4px 0}
.button{display:inline-block;padding:10px 18px;background:#9acaff;color:#102039;border-radius:9px;font-weight:700;text-decoration:none;min-height:44px}
.top{display:flex;align-items:center;flex-wrap:wrap;gap:18px}footer{margin-top:40px;font-size:.9rem}
@media(max-width:600px){nav ul{columns:1}main{padding:24px 18px 50px}}
</style></head><body><main id="top"><div class="top"><a class="button" href="/web/">Open dashboard</a><a href="welcome.html">Welcome / setup help</a></div>
'''
    page += body[0] + '\n' + body[1] + '\n<nav aria-label="Guide contents"><strong>What would you like explained?</strong><ul>' + ''.join(contents) + '</ul></nav>\n'
    page += '\n'.join(body[2:])
    page += '<footer><a href="#top">Back to top</a> · <a href="https://github.com/BlueKF0OZX/BlueNode/blob/main/docs/DASHBOARD_GUIDE.md">Read this guide on GitHub</a></footer></main></body></html>\n'
    return page


if __name__ == '__main__':
    (ROOT / 'web/guide.html').write_text(build(), encoding='utf-8', newline='\n')
