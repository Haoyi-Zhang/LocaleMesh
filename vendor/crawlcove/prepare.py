"""Create a page-only loadable module without altering any evaluated function."""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
raw=(ROOT/'hreflang-upstream.js').read_bytes()
git_blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
assert git_blob=='c04911e67622f6ea0b2b766d1cec9c28077a3658', 'Upstream source differs'
text=raw.decode('utf8')
# Only module dependency pruning. No evaluated page-mode function is modified.
text=text.split('const xml = new XMLParser(')[0]
text=text.replace("import { XMLParser } from 'fast-xml-parser';\n", '')
(ROOT/'page-core.mjs').write_text(text,encoding='utf8')
print('Pinned upstream page functions prepared; sitemap/CLI NOT executed.')
