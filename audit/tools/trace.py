#!/usr/bin/env python3
"""Pine v6 traceability analyzer.
Mechanical screen only -- every hit must be hand-verified. Pine has function-local
scope which this does not model, so locals shadowing globals can produce false hits.
"""
import re, sys, json, collections

KW = set("""and or not if else for while to by var varip switch break continue return
float int bool string color line label box table array matrix map series simple const
input indicator strategy plot plotshape plotchar hline fill bgcolor barcolor alertcondition
alert true false na none export import method type enum""".split())

BUILTIN_PREFIX = ('ta.','math.','array.','str.','color.','line.','label.','box.','table.',
                  'request.','syminfo.','timeframe.','barstate.','strategy.','input.',
                  'plot.','shape.','location.','size.','position.','extend.','xloc.','yloc.',
                  'text.','display.','format.','order.','barmerge.','dayofweek.','session.',
                  'currency.','scale.','alert.','matrix.','map.','runtime.','chart.','ticker.','adjustment.','backadjustment.','settlement.','earnings.','dividends.','splits.')

BUILTIN_VARS = set("""open high low close volume time hl2 hlc3 ohlc4 hlcc4 bar_index
last_bar_index na nz high low open close time_close time_tradingday
dayofweek dayofmonth month year hour minute second weekofyear timenow
""".split())

def strip(src):
    """Remove string literals and // comments, preserving line structure."""
    out=[]
    for ln in src.split('\n'):
        r=''; i=0; n=len(ln); q=None
        while i<n:
            c=ln[i]
            if q:
                if c=='\\': r+='  '; i+=2; continue
                if c==q: q=None; r+=' '
                else: r+=' '
                i+=1; continue
            if c in '"\'':
                q=c; r+=' '; i+=1; continue
            if c=='/' and i+1<n and ln[i+1]=='/':
                r+=' '*(n-i); break
            r+=c; i+=1
        out.append(r)
    return out

TYPES = r'(?:float|int|bool|string|color|line|label|box|table|array<[^>]+>|matrix<[^>]+>|map<[^>]+>|[A-Za-z_]\w*\[\])'
RE_TYPED  = re.compile(r'^\s*(?:var\s+|varip\s+)?'+TYPES+r'\s+([A-Za-z_]\w*)\s*=(?!=)')
RE_PLAIN  = re.compile(r'^\s*(?:var\s+|varip\s+)?([A-Za-z_]\w*)\s*=(?!=)')
RE_TUPLE  = re.compile(r'^\s*\[([^\]]+)\]\s*=(?!=)')
RE_ASSIGN = re.compile(r'([A-Za-z_]\w*)\s*:=')
RE_FUNC   = re.compile(r'^\s*([A-Za-z_]\w*)\s*\(([^)]*)\)\s*=>')
RE_IDENT  = re.compile(r'(?<![\w.])([A-Za-z_]\w*)')
RE_MEMBER = re.compile(r'[A-Za-z_]\w*\.[A-Za-z_]\w*')

def analyze(path):
    src=open(path,encoding='utf-8').read()
    lines=strip(src)
    raw=src.split('\n')
    decl=collections.defaultdict(list)   # name -> [lineno]
    assign=collections.defaultdict(list)
    funcs={}
    fparams=set()
    for i,ln in enumerate(lines,1):
        m=RE_FUNC.match(ln)
        if m:
            funcs[m.group(1)]=i
            for p in m.group(2).split(','):
                p=p.strip().split()[-1] if p.strip() else ''
                if p: fparams.add(p)
            continue
        m=RE_TUPLE.match(ln)
        if m:
            for nm in m.group(1).split(','):
                nm=nm.strip().split()[-1]
                if re.fullmatch(r'[A-Za-z_]\w*',nm or ''): decl[nm].append(i)
            continue
        m=RE_TYPED.match(ln) or RE_PLAIN.match(ln)
        if m and m.group(1) not in KW:
            decl[m.group(1)].append(i)
        for a in RE_ASSIGN.finditer(ln):
            assign[a.group(1)].append(i)

    # occurrence counting, excluding member-access tails
    occ=collections.defaultdict(list)
    for i,ln in enumerate(lines,1):
        masked=RE_MEMBER.sub(lambda m:' '*len(m.group(0)), ln)
        for m in RE_IDENT.finditer(masked):
            nm=m.group(1)
            if nm in KW or nm in BUILTIN_VARS: continue
            occ[nm].append(i)

    names=set(decl)|set(assign)
    rows=[]
    for nm in sorted(names):
        d=set(decl[nm]); a=set(assign[nm])
        # a read = an occurrence on a line that is not solely a decl/assign-target line
        reads=[]
        for i in occ[nm]:
            cnt=len(re.findall(r'(?<![\w.])'+re.escape(nm)+r'(?![\w])', RE_MEMBER.sub(lambda m:' '*len(m.group(0)),lines[i-1])))
            targ=(1 if i in d else 0)+len(re.findall(re.escape(nm)+r'\s*:=',lines[i-1]))
            if cnt>targ: reads.append(i)
        reads=sorted(set(reads))
        rows.append(dict(name=nm, decl=sorted(d), assign=sorted(a), reads=reads,
                         nreads=len(reads), is_param=nm in fparams, is_func=nm in funcs))
    return dict(path=path, nlines=len(raw), rows=rows, funcs=funcs)

if __name__=='__main__':
    res=analyze(sys.argv[1])
    json.dump(res, open(sys.argv[2],'w'))
    dead=[r for r in res['rows'] if r['nreads']==0 and not r['is_param'] and not r['is_func']]
    print(f"{res['path']}  lines={res['nlines']}  symbols={len(res['rows'])}  funcs={len(res['funcs'])}  ZERO-READ={len(dead)}")
