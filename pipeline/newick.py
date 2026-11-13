"""Minimal, iterative Newick reader (handles quoted labels and branch lengths).

A parsed tree is a `Tree`: flat lists indexed by node id, root = 0.
"""
import re

_TOKEN = re.compile(r"\(|\)|,|;|:[^(),;:\[]*|\[[^\]]*\]|'(?:[^']|'')*'|[^(),;:'\[]+")


class Tree:
    __slots__ = ("parent", "label", "length", "children")

    def __init__(self):
        self.parent = []
        self.label = []
        self.length = []
        self.children = []

    def add(self, parent):
        i = len(self.parent)
        self.parent.append(parent)
        self.label.append(None)
        self.length.append(None)
        self.children.append([])
        if parent >= 0:
            self.children[parent].append(i)
        return i

    def __len__(self):
        return len(self.parent)

    def tips(self):
        return [i for i, c in enumerate(self.children) if not c]

    def preorder(self, root=0):
        out, stack = [], [root]
        while stack:
            n = stack.pop()
            out.append(n)
            stack.extend(reversed(self.children[n]))
        return out


def _unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1].replace("''", "'")
    return s


def parse(text):
    """Parse one Newick string (up to the first ';')."""
    t = Tree()
    cur = t.add(-1)
    stack = []
    for m in _TOKEN.finditer(text):
        tok = m.group(0)
        c = tok[0]
        if c == "(":
            stack.append(cur)
            cur = t.add(cur)
        elif c == ",":
            cur = t.add(stack[-1])
        elif c == ")":
            cur = stack.pop()
        elif c == ";":
            break
        elif c == ":":
            v = tok[1:].strip()
            t.length[cur] = float(v) if v else None
        elif c == "[":
            continue  # comment / annotation
        else:
            lab = _unquote(tok)
            if lab:
                t.label[cur] = lab
    return t


def ages(t):
    """Node ages (height above the tips) for a tree with branch lengths. Assumes it is
    (close to) ultrametric: age = max root-to-tip distance - root-to-node distance."""
    dist = [0.0] * len(t)
    for n in t.preorder():
        p = t.parent[n]
        if p >= 0:
            dist[n] = dist[p] + (t.length[n] or 0.0)
    h = max(dist)
    return [max(0.0, h - d) for d in dist]


def extract_clade(text, label_suffix):
    """Return the Newick substring of the clade whose label ends with `label_suffix`
    (e.g. "_ott81461"), including its label. Scans backwards from the label to its
    matching '(' so a huge file never has to be fully parsed."""
    m = re.search(re.escape(label_suffix) + r"'?(?=[,);:])", text)
    if not m:
        raise KeyError(label_suffix)
    end = m.end()
    # Start of the label itself: back up to the previous structural character.
    j = m.start()
    if text[end - 1] == "'":
        j = text.rfind("'", 0, m.start())  # opening quote of a quoted label
    else:
        while j > 0 and text[j - 1] not in "(),;":
            j -= 1
    if j == 0 or text[j - 1] != ")":
        return text[j:end]  # a tip
    depth, in_q, i = 0, False, j - 1
    while i >= 0:
        ch = text[i]
        if ch == "'":
            in_q = not in_q
        elif not in_q:
            if ch == ")":
                depth += 1
            elif ch == "(":
                depth -= 1
                if depth == 0:
                    return text[i:end]
        i -= 1
    raise ValueError("unbalanced Newick")


def read_trees(path, limit=None):
    """Yield Newick strings from a file: plain (one per line) or NEXUS with a TRANSLATE
    block. Returns (newick, translate_dict_or_None) pairs."""
    with open(path) as f:
        head = f.read(64)
        f.seek(0)
        if head.lstrip().upper().startswith("#NEXUS"):
            yield from _read_nexus(f, limit)
            return
        n = 0
        for line in f:
            line = line.strip()
            if not line.startswith("("):
                continue
            yield line, None
            n += 1
            if limit and n >= limit:
                return


def _read_nexus(f, limit):
    translate, in_tr, n = None, False, 0
    for line in f:
        s = line.strip()
        u = s.upper()
        if u.startswith("TRANSLATE"):
            translate, in_tr = {}, True
            continue
        if in_tr:
            for part in s.rstrip(";").split(","):
                part = part.strip()
                if part:
                    k, v = part.split(None, 1)
                    translate[k] = _unquote(v)
            if s.endswith(";"):
                in_tr = False
            continue
        if u.startswith("TREE "):
            nwk = s[s.index("(") if "(" in s else 0:]
            yield nwk, translate
            n += 1
            if limit and n >= limit:
                return
