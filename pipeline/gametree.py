"""Turn an Open Tree clade into a game tree: species tips only, single-child nodes
suppressed, and divergence dates overlaid from one or more dated trees."""
import statistics

import newick
import opentree


class GameTree:
    """Tips are nodes 0..n-1 (in tree order); internal nodes follow. Parent of the root is -1.
    names[node] lists the OTT ids of every named taxon that collapsed onto that node,
    most inclusive last."""

    def __init__(self):
        self.tips = []        # ott id of each tip
        self.parent = []
        self.children = []
        self.names = []
        self.age = []         # Myr; 0 for tips; None until dated

    @property
    def n(self):
        return len(self.tips)

    def preorder(self):
        root = self.parent.index(-1)
        out, stack = [], [root]
        while stack:
            x = stack.pop()
            out.append(x)
            stack.extend(reversed(self.children[x]))
        return out


def from_clades(clades, keep_tip, exclude=()):
    """Build a GameTree from Open Tree clades (newick.Tree list, joined under one root).
    keep_tip(ott_id) says whether a taxon is a playable species; its descendants
    (subspecies) are dropped. Subtrees rooted at an ott id in `exclude` are skipped."""
    exclude = set(exclude)
    nodes = []   # (kind, ott_or_None, children, names) built bottom-up; index = temp id

    def make(kind, ott, kids, names):
        nodes.append([kind, ott, kids, names])
        return len(nodes) - 1

    tops = []
    for t in clades:
        result = [None] * len(t)
        order = t.preorder()
        is_tip = [False] * len(t)
        skip = [False] * len(t)
        for x in order:  # mark tips and skipped subtrees top-down
            p = t.parent[x]
            if p >= 0 and (skip[p] or is_tip[p]):
                skip[x] = True
                continue
            o = opentree.ott_id(t.label[x])
            if o in exclude:
                skip[x] = True
            elif o is not None and keep_tip(o):
                is_tip[x] = True
        for x in reversed(order):  # bottom-up
            if skip[x]:
                continue
            o = opentree.ott_id(t.label[x])
            if is_tip[x]:
                result[x] = make("tip", o, [], [])
                continue
            kids = [result[c] for c in t.children[x] if result[c] is not None]
            if not kids:
                continue
            if len(kids) == 1:
                k = kids[0]
                if o is not None and nodes[k][0] == "int":
                    nodes[k][3].append(o)
                result[x] = k
                continue
            result[x] = make("int", None, kids, [o] if o is not None else [])
        if result[0] is not None:
            tops.append(result[0])
    root = tops[0] if len(tops) == 1 else make("int", None, tops, [])

    # Re-index: tips first in tree order, then internal nodes.
    order, stack = [], [root]
    while stack:
        x = stack.pop()
        order.append(x)
        stack.extend(reversed(nodes[x][2]))
    tips = [x for x in order if nodes[x][0] == "tip"]
    ints = [x for x in order if nodes[x][0] == "int"]
    new = {x: i for i, x in enumerate(tips + ints)}
    g = GameTree()
    total = len(new)
    g.parent = [-1] * total
    g.children = [[] for _ in range(total)]
    g.names = [[] for _ in range(total)]
    g.age = [None] * total
    g.tips = [nodes[x][1] for x in tips]
    for x, i in new.items():
        g.children[i] = [new[c] for c in nodes[x][2]]
        for c in g.children[i]:
            g.parent[c] = i
        g.names[i] = list(nodes[x][3])
        if nodes[x][0] == "tip":
            g.age[i] = 0.0
    return g


def prune(g, keep):
    """A new GameTree with only the tips i where keep(i) (indexes into g's tips), single-
    child nodes suppressed. Returns (tree, old_tip_index_list)."""
    out = [None] * len(g.parent)
    nodes = []

    def make(kind, src, kids, names):
        nodes.append([kind, src, kids, names])
        return len(nodes) - 1

    order = g.preorder()
    for x in reversed(order):
        if x < g.n:
            out[x] = make("tip", x, [], []) if keep(x) else None
            continue
        kids = [out[c] for c in g.children[x] if out[c] is not None]
        if not kids:
            continue
        if len(kids) == 1:
            k = kids[0]
            if nodes[k][0] == "int":
                nodes[k][3].extend(g.names[x])
            out[x] = k
            continue
        out[x] = make("int", x, kids, list(g.names[x]))
    root = out[order[0]]
    seq, stack = [], [root]
    while stack:
        x = stack.pop()
        seq.append(x)
        stack.extend(reversed(nodes[x][2]))
    tips = [x for x in seq if nodes[x][0] == "tip"]
    ints = [x for x in seq if nodes[x][0] == "int"]
    new = {x: i for i, x in enumerate(tips + ints)}
    h = GameTree()
    total = len(new)
    h.parent = [-1] * total
    h.children = [[] for _ in range(total)]
    h.names = [[] for _ in range(total)]
    h.age = [None] * total
    h.tips = [g.tips[nodes[x][1]] for x in tips]
    for x, i in new.items():
        h.children[i] = [new[c] for c in nodes[x][2]]
        for c in h.children[i]:
            h.parent[c] = i
        h.names[i] = list(nodes[x][3])
        # Ages carry over: the MRCA of the kept tips under x is x itself (x kept >= 2 kids).
        h.age[i] = g.age[nodes[x][1]]
    return h, [nodes[x][1] for x in tips]


class _Dated:
    """A dated tree prepared for LCA queries."""

    def __init__(self, t):
        self.t = t
        self.age = newick.ages(t)
        self.pre = [0] * len(t)
        self.depth = [0] * len(t)
        order = t.preorder()
        self.by_pre = order
        for i, x in enumerate(order):
            self.pre[x] = i
            p = t.parent[x]
            if p >= 0:
                self.depth[x] = self.depth[p] + 1

    def lca(self, a, b):
        par, dep = self.t.parent, self.depth
        while dep[a] > dep[b]:
            a = par[a]
        while dep[b] > dep[a]:
            b = par[b]
        while a != b:
            a, b = par[a], par[b]
        return a


def date(g, dated_trees, tip_of_label):
    """Fill g.age from dated trees. tip_of_label(label) -> game tip index or None.
    Each game node gets the median, across trees, of the age of the MRCA (in that tree)
    of its descendant tips that the tree contains; nodes the trees can't date are
    interpolated. Returns (dated_nodes, interpolated_nodes, matched_tips)."""
    samples = [[] for _ in range(len(g.parent))]
    order = g.preorder()
    matched = set()
    for t in dated_trees:
        d = _Dated(t)
        at = {}
        for x in t.tips():
            i = tip_of_label(t.label[x])
            if i is not None:
                at[i] = x
        matched.update(at)
        lo = [None] * len(g.parent)
        hi = [None] * len(g.parent)
        cnt = [0] * len(g.parent)
        for x in reversed(order):
            if x < g.n:
                if x in at:
                    lo[x] = hi[x] = at[x]
                    cnt[x] = 1
                continue
            for c in g.children[x]:
                if cnt[c]:
                    cnt[x] += cnt[c]
                    if lo[x] is None or d.pre[lo[c]] < d.pre[lo[x]]:
                        lo[x] = lo[c]
                    if hi[x] is None or d.pre[hi[c]] > d.pre[hi[x]]:
                        hi[x] = hi[c]
            if cnt[x] >= 2:
                samples[x].append(d.age[d.lca(lo[x], hi[x])])
    dated = 0
    for x in range(g.n, len(g.parent)):
        if samples[x]:
            g.age[x] = statistics.median(samples[x])
            dated += 1
    # Monotone: a node is at least as old as any dated descendant.
    below = [0.0] * len(g.parent)  # oldest dated age at or below x
    height = [0] * len(g.parent)   # edges to the deepest tip
    for x in reversed(order):
        if x < g.n:
            continue
        b = max(below[c] for c in g.children[x])
        height[x] = 1 + max(height[c] for c in g.children[x])
        if g.age[x] is not None:
            g.age[x] = max(g.age[x], b)
            b = g.age[x]
        below[x] = b
    root = order[0]
    if g.age[root] is None:
        g.age[root] = below[root] * 1.1 or 1.0
    # Undated nodes: spread evenly between the parent's age and the oldest dated node below.
    interp = 0
    for x in order:
        if g.age[x] is None:
            pa = g.age[g.parent[x]]
            lo_age = below[x]
            g.age[x] = lo_age + (pa - lo_age) * height[x] / (height[x] + 1)
            interp += 1
    return dated, interp, len(matched)
