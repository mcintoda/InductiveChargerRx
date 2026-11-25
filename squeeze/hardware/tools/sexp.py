"""Minimal S-expression reader/writer for KiCad files."""
import re

_tok = re.compile(r'\s*(?:(\()|(\))|("(?:[^"\\]|\\.)*")|([^\s()"]+))')


class Sym(str):
    """Bare (unquoted) atom."""


def parse(text):
    stack, cur, pos = [], [], 0
    while True:
        m = _tok.match(text, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        o, c, q, a = m.groups()
        if o:
            stack.append(cur); cur = []
        elif c:
            done = cur; cur = stack.pop(); cur.append(done)
        elif q is not None:
            cur.append(q[1:-1].replace('\\"', '"').replace('\\\\', '\\'))
        else:
            cur.append(Sym(a))
    return cur[0]


def dump(x, ind=0):
    if isinstance(x, list):
        if all(not isinstance(e, list) for e in x):
            return "(" + " ".join(dump(e) for e in x) + ")"
        out, i = "(", 0
        while i < len(x) and not isinstance(x[i], list):  # leading atoms inline
            out += ("" if i == 0 else " ") + dump(x[i]); i += 1
        for e in x[i:]:  # keep original order for the rest
            out += "\n" + "  " * (ind + 1) + dump(e, ind + 1)
        return out + "\n" + "  " * ind + ")"
    if isinstance(x, Sym):
        return str(x)
    if isinstance(x, (int, float)):
        return repr(round(x, 4)) if isinstance(x, float) else str(x)
    return '"' + str(x).replace('\\', '\\\\').replace('"', '\\"') + '"'


def find(node, key):
    return [e for e in node if isinstance(e, list) and e and e[0] == key]
