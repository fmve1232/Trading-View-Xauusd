#!/usr/bin/env python3
"""Declaration-BEFORE-USE checker for Pine v6 global scope.

Pine requires an identifier be declared textually before it is used. A use inside a
function body may refer to that function's params/locals, or to a global declared before
the FUNCTION DEFINITION line. This is what `undeclared.py` missed: it only asked whether a
name was bound anywhere in the file.
"""
import re,sys

def strip_code(src):
    out=[]
    for ln in src.split('\n'):
        r='';i=0;n=len(ln);q=None
        while i<n:
            c=ln[i]
            if q:
                if c=='\\': r+='  ';i+=2;continue
                if c==q: q=None
                r+=' ';i+=1;continue
            if c in '"\'': q=c;r+=' ';i+=1;continue
            if c=='/' and i+1<n and ln[i+1]=='/': r+=' '*(n-i);break
            r+=c;i+=1
        out.append(r)
    return out

HEX=re.compile(r'#[0-9A-Fa-f]{3,8}')
NAMED=re.compile(r'(?<![=!<>])\b([A-Za-z_]\w*)\s*=(?![=])')
TYPES=r'(?:float|int|bool|string|color|line|label|box|table|array<[^>]*>|matrix<[^>]*>|map<[^>]*>|[A-Za-z_]\w*\[\])'
BUILTIN=set("""open high low close volume time hl2 hlc3 ohlc4 hlcc4 bar_index last_bar_index
last_bar_time na nz true false time_close time_tradingday syminfo timeframe barstate strategy
ta math array str color line label box table request input indicator plot plotshape plotchar
plotcandle plotarrow plotbar hline fill bgcolor barcolor alertcondition alert fixnan dayofweek
dayofmonth month year hour minute second weekofyear timenow dayofyear matrix map runtime chart
ticker adjustment session currency scale shape location size position extend xloc yloc text
display format order barmerge float int bool string var varip switch export import method type
enum series simple const and or not if else for while to by break continue return""".split())

def check(path):
    S=strip_code(open(path,encoding='utf-8').read())
    n=len(S)
    # pass 1: global declarations (indent 0) and function definition spans
    gdecl={}      # name -> first global decl line
    fdef={}       # func name -> (defline, endline, {params/locals: line})
    named=set()
    cur=None
    for i,l in enumerate(S,1):
        L=HEX.sub(' ',l)
        for m in NAMED.finditer(L):
            if '(' in L[:m.start()]: named.add(m.group(1))
        ind=len(L)-len(L.lstrip(' '))
        if L.strip() and ind==0 and cur: cur=None
        m=re.match(r'^([A-Za-z_]\w*)\s*\((.*)\)\s*=>',L)
        if m:
            fdef[m.group(1)]={'def':i,'locals':{}}
            gdecl.setdefault(m.group(1),i)
            for p in m.group(2).split(','):
                p=p.strip()
                if p:
                    t=p.split()[-1]
                    if re.fullmatch(r'[A-Za-z_]\w*',t): fdef[m.group(1)]['locals'][t]=i
            cur=m.group(1); continue
        target=fdef[cur]['locals'] if (cur and ind>0) else gdecl
        m=re.match(r'^\s*\[([^\]]+)\]\s*=(?!=)',L)
        if m:
            for nm in m.group(1).split(','):
                nm=nm.strip().split()[-1] if nm.strip() else ''
                if re.fullmatch(r'[A-Za-z_]\w*',nm or ''): target.setdefault(nm,i)
            continue
        for m2 in re.finditer(r'\bfor\s+([A-Za-z_]\w*)\s*(?:=|\bin\b)',L): target.setdefault(m2.group(1),i)
        m=re.match(r'^\s*(?:var\s+|varip\s+)?(?:'+TYPES+r'\s+)?([A-Za-z_]\w*)\s*=(?!=)',L)
        if m: target.setdefault(m.group(1),i)
        for m2 in re.finditer(r'\b([A-Za-z_]\w*)\s*:=',L): target.setdefault(m2.group(1),i)

    # pass 2: uses
    bad=[]
    cur=None; curind=0
    for i,l in enumerate(S,1):
        L=HEX.sub(' ',l)
        ind=len(L)-len(L.lstrip(' '))
        if L.strip() and ind==0 and cur and not re.match(r'^([A-Za-z_]\w*)\s*\(.*\)\s*=>',L): cur=None
        m=re.match(r'^([A-Za-z_]\w*)\s*\(.*\)\s*=>',L)
        if m: cur=m.group(1); continue
        scan=re.sub(r'[A-Za-z_]\w*\.[A-Za-z_]\w*',' ',L)
        scan=NAMED.sub(' ',scan)
        for m2 in re.finditer(r'(?<![\w.])([A-Za-z_]\w*)',scan):
            nm=m2.group(1)
            if nm in BUILTIN or nm in named: continue
            if cur and nm in fdef[cur]['locals']:
                if fdef[cur]['locals'][nm]<=i: continue
            gl=gdecl.get(nm)
            if gl is None: continue                      # undeclared: undeclared.py's job
            limit = fdef[cur]['def'] if cur else i
            if gl > limit:
                bad.append((i,nm,gl,cur))
    return bad

for p in sys.argv[1:]:
    b=check(p)
    print(f"{p.split('/')[-1]}: {len(b)} order violation(s)")
    seen=set()
    for i,nm,gl,fn in b:
        if nm in seen: continue
        seen.add(nm)
        where=f"inside {fn}() defined L{ check.__self__ if False else ''}" if fn else "global scope"
        print(f"    L{i:<6} uses '{nm}' declared later at L{gl}   ({'in '+fn+'()' if fn else 'global'})")
