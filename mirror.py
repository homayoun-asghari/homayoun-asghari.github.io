"""
A second copy of homayoun.me, as plain files, for GitHub Pages.

It downloads the live site exactly as it is: every page, every file a page
uses, every attachment. Nothing is rebuilt, so the copy cannot drift from the
original. The Vercel address is used rather than homayoun.me because
Cloudflare rewrites the email link into something that only works behind
Cloudflare.

It refuses to replace a good copy with a bad one. If any download fails, or the
site suddenly looks nothing like the last copy (for example a parking page after
the domain lapsed), it exits without writing anything.

    python3 mirror.py docs
"""

import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urldefrag, urlparse

ORIGIN = "https://the-arrival-phi.vercel.app"
PUBLIC = "https://homayoun.me"

# The pages, and the files that no page links to but that the site serves.
PAGES = {"/": "index.html", "/logs": "logs.html"}
EXTRA = [
    "/rss.xml", "/feed.json", "/sitemap.xml", "/robots.txt", "/manifest.webmanifest",
    "/icon.svg", "/favicon.ico", "/apple-touch-icon.png", "/icon-192.png", "/icon-512.png",
    "/opengraph-image",
]
NOT_FOUND_PROBE = "/this-page-does-not-exist-mirror-probe"

# Same-site paths worth following out of HTML, CSS and JS.
LINK = re.compile(r"""(?:href|src)=["'](/[^"'#?]*)""")
CSS_URL = re.compile(r"""url\(\s*["']?(/[^"')?#]+)""")
JS_ASSET = re.compile(r"""["'`](?:/_next/)?(static/immutable/[A-Za-z0-9_./-]+\.(?:js|css|woff2|woff|png|svg|jpg))["'`]""")


def fetch(path):
    req = urllib.request.Request(ORIGIN + path, headers={"User-Agent": "site-mirror/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read()


def fetch_404():
    req = urllib.request.Request(ORIGIN + NOT_FOUND_PROBE, headers={"User-Agent": "site-mirror/1.0"})
    try:
        urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return e.read()
    raise SystemExit("The not-found page did not answer 404.")


def wanted(path):
    if path.startswith(("/admin", "/api/", "/cdn-cgi/", "/_vercel/")):
        return False
    return path not in PAGES


def localize(html):
    """Links back to homayoun.me stay on the copy. Canonical and share tags keep the real address."""
    return re.sub(r'(<a\b[^>]*\bhref=")https://homayoun\.me(?=[/"#])', r"\1", html)


def main(out):
    tmp = tempfile.mkdtemp()
    files = {}
    queue = list(EXTRA)

    for path, name in PAGES.items():
        status, body = fetch(path)
        html = body.decode("utf-8")
        files[name] = localize(html).encode("utf-8")
        queue += [urldefrag(p)[0] for p in LINK.findall(html)]
    files["404.html"] = localize(fetch_404().decode("utf-8")).encode("utf-8")
    queue += LINK.findall(files["404.html"].decode("utf-8"))

    seen = set()
    while queue:
        path = queue.pop()
        if not path or path in seen or not wanted(path):
            continue
        seen.add(path)
        try:
            _, body = fetch(path)
        except urllib.error.HTTPError as e:
            raise SystemExit(f"{path} answered {e.code}. Nothing was written.")
        files[path.lstrip("/")] = body
        if path.endswith(".css"):
            queue += CSS_URL.findall(body.decode("utf-8", "replace"))
        if path.endswith(".js"):
            queue += ["/_next/" + p for p in JS_ASSET.findall(body.decode("utf-8", "replace"))]

    # The guard: a real copy of this site has its name, its logs and its files.
    logs = files["logs.html"].decode("utf-8")
    attachments = sum(1 for k in files if k.startswith("attachments/"))
    if "Homayoun Asghari" not in logs or attachments == 0:
        raise SystemExit("This does not look like the site. Nothing was written.")
    manifest = os.path.join(out, "mirror.json")
    if os.path.exists(manifest):
        before = json.load(open(manifest))
        if attachments < before["attachments"] // 2 or len(files) < before["files"] // 2:
            raise SystemExit(
                f"Half the site is missing ({len(files)} files, was {before['files']}). Nothing was written."
            )

    for name, body in files.items():
        dest = os.path.join(tmp, name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(body)
    open(os.path.join(tmp, ".nojekyll"), "w").close()  # GitHub would otherwise hide /_next
    with open(os.path.join(tmp, "mirror.json"), "w") as f:
        json.dump({"files": len(files), "attachments": attachments}, f)

    if os.path.exists(out):
        shutil.rmtree(out)
    shutil.move(tmp, out)
    print(f"{len(files)} files, {attachments} attachments")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs")
