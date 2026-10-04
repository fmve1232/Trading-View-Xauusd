#!/usr/bin/env python3
"""Execute selected Pine v6 source lines in Python, so formulas can be checked AS WRITTEN.

formula_check.py and race_model_check.py re-type the maths; a transcription error in the
.pine would not show up there. This module reads the lines out of the artefact itself and
runs them: expressions (ternary, and/or/not, comparisons, arithmetic, calls, [i] history on
plain lists), and statements (typed/untyped declarations, :=, +=, -=, *=, /=, if / else if /
else blocks, for i = a to b). Only the subset the checked blocks use; anything else raises.

`na` is float('nan'). Pine semantics kept where they matter for the checked blocks:
na(x), nz(x, y), math.max/min propagate na, int() truncates toward zero, math.round
rounds half away from zero, comparisons with na are False.
Not modelled: series history across bars, tolerance-based float equality (F-A37), tables.

Usage: imported by formula_trace.py.
"""
import math
import re

TOK = re.compile(r'\s*(?:(\d+\.\d*(?:e[-+]?\d+)?|\d+(?:e[-+]?\d+)?|\.\d+)|("(?:\\.|[^"\\])*")|'
                 r'([A-Za-z_][A-Za-z0-9_.]*)|(:=|==|!=|<=|>=|\+=|-=|\*=|/=|=>|[-+*/%<>?:()\[\],=]))')
NA = float('nan')


class Series(list):
    """A price/volume series, oldest first: a bare name reads the current bar, name[i] reads i bars back."""


def isna(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def _round(x, d=None):
    if isna(x):
        return NA
    if d is None:
        return float(math.floor(abs(x) + 0.5) * (1 if x >= 0 else -1))
    m = 10 ** d
    return math.floor(abs(x) * m + 0.5) / m * (1 if x >= 0 else -1)


def _mx(*a):
    return NA if any(isna(v) for v in a) else max(a)


def _mn(*a):
    return NA if any(isna(v) for v in a) else min(a)


def _tostr(x, fmt=None):
    """str.tostring with the '#.##' style masks the artefacts use (round half away, trim zeros)."""
    if isinstance(x, str):
        return x
    if isinstance(x, bool):
        return 'true' if x else 'false'
    if isna(x):
        return 'NaN'
    if fmt is None or not isinstance(fmt, str) or not set(fmt) <= set('#.0'):
        d = 6 if fmt is None else 0
    else:
        d = len(fmt.split('.', 1)[1]) if '.' in fmt else 0
    v = _round(x, d) if d else _round(x)
    out = f"{v:.{d}f}" if d else str(int(v))
    if '.' in out:
        out = out.rstrip('0').rstrip('.')
    return '0' if out in ('-0', '') else out


BUILTINS = {
    'str.tostring': _tostr,
    'math.sqrt': lambda x: NA if isna(x) or x < 0 else math.sqrt(x),
    'math.exp': lambda x: NA if isna(x) else math.exp(x),
    'math.log': lambda x: NA if isna(x) or x <= 0 else math.log(x),
    'math.abs': lambda x: NA if isna(x) else abs(x),
    'math.pow': lambda x, y: NA if isna(x) or isna(y) else math.pow(x, y),
    'math.max': _mx, 'math.min': _mn, 'math.round': _round,
    'math.floor': lambda x: NA if isna(x) else float(math.floor(x)),
    'math.ceil': lambda x: NA if isna(x) else float(math.ceil(x)),
    'na': isna, 'nz': lambda x, y=0.0: y if isna(x) else x,
    'int': lambda x: NA if isna(x) else int(x), 'float': lambda x: float(x),
    'array.get': lambda a, i: a[int(i)],
    'array.from': lambda *a: list(a),
    'array.new_float': lambda n, v=NA: [v] * int(n),
    'array.sum': lambda a: sum(x for x in a if not isna(x)),
}


class Parser:
    def __init__(self, src):
        self.t = [m for m in TOK.findall(src.split('//')[0] if '"' not in src else src)]
        self.t = [next(x for x in m if x) for m in self.t]
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self, v=None):
        tk = self.peek()
        if v is not None and tk != v:
            raise SyntaxError(f"expected {v!r}, got {tk!r} in {' '.join(self.t)}")
        self.i += 1
        return tk

    def expr(self):
        c = self.orx()
        if self.peek() == '?':
            self.take('?')
            a = self.expr()
            self.take(':')
            b = self.expr()
            return f"(({a}) if _T({c}) else ({b}))"
        return c

    def orx(self):
        a = self.andx()
        while self.peek() == 'or':
            self.take()
            a = f"(_T({a}) or _T({self.andx()}))"
        return a

    def andx(self):
        a = self.notx()
        while self.peek() == 'and':
            self.take()
            a = f"(_T({a}) and _T({self.notx()}))"
        return a

    def notx(self):
        if self.peek() == 'not':
            self.take()
            return f"(not _T({self.notx()}))"
        return self.cmp()

    def cmp(self):
        a = self.add()
        while self.peek() in ('==', '!=', '<', '>', '<=', '>='):
            op = self.take()
            a = f"_C({a!s}, {op!r}, {self.add()})"
        return a

    def add(self):
        a = self.mul()
        while self.peek() in ('+', '-'):
            op = self.take()
            a = f"_A({a}, {op!r}, {self.mul()})"
        return a

    def mul(self):
        a = self.un()
        while self.peek() in ('*', '/', '%'):
            op = self.take()
            a = f"_A({a}, {op!r}, {self.un()})"
        return a

    def un(self):
        if self.peek() == '-':
            self.take()
            return f"_A(0.0, '-', {self.un()})"
        return self.post()

    def post(self):
        a = self.prim()
        while self.peek() in ('(', '['):
            if self.take() == '(':
                args = []
                while self.peek() != ')':
                    if re.fullmatch(r'[A-Za-z_]\w*', self.peek() or '') and self.t[self.i + 1:self.i + 2] == ['=']:
                        self.i += 2          # named argument: keep the value only
                    args.append(self.expr())
                    if self.peek() == ',':
                        self.take()
                self.take(')')
                mname = re.fullmatch(r"_V\('([\w.]+)'\)", a)
                fname = mname.group(1) if mname else a
                a = f"_F({fname!r}, {', '.join(args)})" if args else f"_F({fname!r})"
            else:
                idx = self.expr()
                self.take(']')
                mh = re.fullmatch(r"_V\('([\w.]+)'\)", a)
                a = f"_HS({mh.group(1)!r}, {idx})" if mh else f"_H({a}, {idx})"
        return a

    def prim(self):
        tk = self.take()
        if tk == '(':
            e = self.expr()
            self.take(')')
            return e
        if tk in ('true', 'false'):
            return 'True' if tk == 'true' else 'False'
        if tk == 'na':
            if self.peek() == '(':
                return 'na'
            return 'NA'
        if re.fullmatch(r'[\d.].*', tk):
            return repr(float(tk))
        if tk.startswith('"'):
            return tk
        return f"_V({tk!r})"


def compile_expr(src):
    p = Parser(src)
    code = p.expr()
    if p.peek() is not None:
        raise SyntaxError(f"trailing {p.t[p.i:]} in {src!r}")
    return code


def _T(x):
    return False if isna(x) else bool(x)


def _C(a, op, b):
    if isna(a) or isna(b):
        return False
    return {'==': a == b, '!=': a != b, '<': a < b, '>': a > b, '<=': a <= b, '>=': a >= b}[op]


def _A(a, op, b):
    if isinstance(a, str) or isinstance(b, str):
        return a + b
    if isna(a) or isna(b):
        return NA
    if op == '/':
        return NA if b == 0 else a / b
    if op == '%':
        return math.fmod(a, b) if b and math.isfinite(a) else NA
    return a + b if op == '+' else a - b if op == '-' else a * b


class Env(dict):
    def __init__(self, funcs=None, **kw):
        super().__init__(**kw)
        self.funcs = funcs or {}


def evaluate(src, env):
    code = compile_expr(src)
    g = {'_T': _T, '_C': _C, '_A': _A, 'NA': NA, 'na': 'na',
         '_V': lambda n: (env[n][-1] if isinstance(env[n], Series) else env[n]) if n in env else (_ for _ in ()).throw(NameError(n)),
         '_H': lambda a, i: a if isinstance(a, (int, float)) and int(i) == 0 else NA,
         '_HS': lambda nm, i: (lambda v, k: (v[-1 - k] if k < len(v) else NA) if isinstance(v, Series)
                               else (v if k == 0 else NA))(env[nm], int(i)),
         '_F': lambda f, *a: (env.funcs[f](*a) if f in env.funcs else BUILTINS[f](*a))}
    return eval(code, g)


DECL = re.compile(r'^(?:var\s+)?(?:float|int|bool|string|color|float\[\]|int\[\]|array<\w+>)\s+([A-Za-z_]\w*)\s*=\s*(.+)$')
PLAIN = re.compile(r'^([A-Za-z_]\w*)\s*(:=|\+=|-=|\*=|/=|=)\s*(.+)$')
SETA = re.compile(r'^array\.set\(\s*([A-Za-z_]\w*)\s*,(.+)$')


class _Break(Exception):
    pass


def run(lines, env):
    """Run a list of Pine source lines (indentation preserved) in env."""
    lines = [l.split('//')[0].rstrip() if '"' not in l else l.rstrip() for l in lines]
    lines = [l for l in lines if l.strip()]
    _block(lines, 0, len(lines), env)
    return env


def _ind(l):
    return len(l) - len(l.lstrip(' '))


def _block(L, a, b, env):
    i = a
    while i < b:
        line = L[i]
        s = line.strip()
        base = _ind(line)
        j = i + 1
        while j < b and _ind(L[j]) > base:
            j += 1
        m = re.match(r'^if\s+(.+)$', s)
        if m:
            chain = [(m.group(1), i + 1, j)]
            while j < b and _ind(L[j]) == base and re.match(r'^else\b', L[j].strip()):
                es = L[j].strip()
                k = j + 1
                while k < b and _ind(L[k]) > base:
                    k += 1
                mm = re.match(r'^else\s+if\s+(.+)$', es)
                chain.append((mm.group(1) if mm else None, j + 1, k))
                j = k
            for cond, s0, s1 in chain:
                if cond is None or _T(evaluate(cond, env)):
                    _block(L, s0, s1, env)
                    break
            i = j
            continue
        m = re.match(r'^while\s+(.+)$', s)
        if m:
            try:
                while _T(evaluate(m.group(1), env)):
                    _block(L, i + 1, j, env)
            except _Break:
                pass
            i = j
            continue
        if s == 'break':
            raise _Break()
        m = re.match(r'^for\s+([A-Za-z_]\w*)\s*=\s*(.+?)\s+to\s+(.+)$', s)
        if m:
            lo, hi = int(evaluate(m.group(2), env)), int(evaluate(m.group(3), env))
            try:
                for v in range(lo, hi + 1) if hi >= lo else range(lo, hi - 1, -1):
                    env[m.group(1)] = v
                    _block(L, i + 1, j, env)
            except _Break:
                pass
            i = j
            continue
        m = SETA.match(s)
        if m:
            arr = env[m.group(1)]
            parts = _split_args(m.group(2).rsplit(')', 1)[0])
            arr[int(evaluate(parts[0], env))] = evaluate(parts[1], env)
            i = j
            continue
        m = DECL.match(s)
        if m:
            env[m.group(1)] = evaluate(m.group(2), env)
            i = j
            continue
        m = PLAIN.match(s)
        if m:
            n, op, e = m.groups()
            v = evaluate(e, env)
            env[n] = v if op in ('=', ':=') else _A(env[n], op[0], v)
            i = j
            continue
        raise SyntaxError(f"unsupported statement: {s!r}")


def _split_args(s):
    out, depth, cur = [], 0, ''
    for ch in s:
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur)
            cur = ''
        else:
            cur += ch
    out.append(cur)
    return [x.strip() for x in out]


def extract(path, start_pat, end_pat, include_end=True):
    """Return the source lines from the first line matching start_pat to end_pat."""
    L = open(path, encoding='utf-8').read().split('\n')
    a = next(i for i, l in enumerate(L) if re.search(start_pat, l))
    b = next(i for i in range(a, len(L)) if re.search(end_pat, L[i]))
    blk = L[a:b + 1 if include_end else b]
    base = min(_ind(l) for l in blk if l.strip() and not l.strip().startswith('//'))
    return [l[base:] if l.strip() else l for l in blk], a + 1
