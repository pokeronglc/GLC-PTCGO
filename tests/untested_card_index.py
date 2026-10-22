"""display name -> 'SET.Module' for test scenarios (first printing found)."""
import glob
import os
import re

_ROOT = os.path.join(os.path.dirname(__file__), '..', 'spirit', 'game', 'scripts', 'cards')
_INDEX = None


def card(name):
    global _INDEX
    if _INDEX is None:
        _INDEX = {}
        for f in sorted(glob.glob(os.path.join(_ROOT, '*', '*.py'))):
            try:
                with open(f, encoding='utf-8') as fh:
                    src = fh.read()
            except OSError:
                continue
            m = re.search(r'display_name\s*=\s*["\']([^"\']+)["\']', src)
            if m:
                _INDEX.setdefault(m.group(1), os.path.basename(os.path.dirname(f)) + '.' + os.path.basename(f)[:-3])
    return _INDEX[name]
