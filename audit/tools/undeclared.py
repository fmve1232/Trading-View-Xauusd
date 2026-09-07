#!/usr/bin/env python3
"""Report identifiers used but never bound, excluding Pine's binding forms.
Heuristic: false positives are possible, false NEGATIVES are the risk we care about."""
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
NAMEDARG=re.compile(r'(?<![=!<>])\b([A-Za-z_]\w*)\s*=(?![=])')
TYPES=r'(?:float|int|bool|string|color|line|label|box|table|array<[^>]*>|matrix<[^>]*>|map<[^>]*>|[A-Za-z_]\w*\[\])'

BUILTIN=set("""open high low close volume time hl2 hlc3 ohlc4 hlcc4 bar_index last_bar_index
last_bar_time na nz true false time_close time_tradingday syminfo timeframe barstate strategy
ta math array str color line label box table request input indicator plot plotshape plotchar
plotcandle plotarrow plotbar hline fill bgcolor barcolor alertcondition alert fixnan dayofweek
dayofmonth month year hour minute second weekofyear timenow dayofyear matrix map runtime chart
ticker adjustment session currency scale shape location size position extend xloc yloc text
display format order barmerge float int bool string var varip switch export import method type
enum series simple const and or not if else for while to by break continue return""".split())

def analyze(path):
    S=strip_code(open(path,encoding='utf-8').read())
    bound=set(); named=set()
    for l in S:
        L=HEX.sub(' ',l)
        # function definitions + their params (params may span the whole signature)
        m=re.match(r'^\s*([A-Za-z_]\w*)\s*\((.*)\)\s*=>',L)
        if m:
            bound.add(m.group(1))
            for p in m.group(2).split(','):
                p=p.strip()
                if p:
                    tok=p.split()[-1]
                    if re.fullmatch(r'[A-Za-z_]\w*',tok): bound.add(tok)
            continue
        # tuple destructuring, any indent
        m=re.match(r'^\s*\[([^\]]+)\]\s*=(?!=)',L)
        if m:
            for nm in m.group(1).split(','):
                nm=nm.strip().split()[-1] if nm.strip() else ''
                if re.fullmatch(r'[A-Za-z_]\w*',nm or ''): bound.add(nm)
            continue
        # for-loop variables
        for m2 in re.finditer(r'\bfor\s+([A-Za-z_]\w*)\s*(?:=|\bin\b)',L): bound.add(m2.group(1))
        # typed or plain declaration, any indent
        m=re.match(r'^\s*(?:var\s+|varip\s+)?(?:'+TYPES+r'\s+)?([A-Za-z_]\w*)\s*=(?!=)',L)
        if m: bound.add(m.group(1))
        for m2 in re.finditer(r'\b([A-Za-z_]\w*)\s*:=',L): bound.add(m2.group(1))
        # named arguments inside calls  ->  never identifiers
        for m2 in NAMEDARG.finditer(L):
            if '(' in L[:m2.start()]: named.add(m2.group(1))
    unresolved={}
    for i,l in enumerate(S,1):
        L=HEX.sub(' ',l)
        L=re.sub(r'[A-Za-z_]\w*\.[A-Za-z_]\w*',' ',L)          # member access
        L=NAMEDARG.sub(' ',L)                                   # named args
        for m in re.finditer(r'(?<![\w.])([A-Za-z_]\w*)',L):
            n=m.group(1)
            if n in BUILTIN or n in bound or n in named: continue
            unresolved.setdefault(n,[]).append(i)
    return unresolved

for p in sys.argv[1:]:
    u=analyze(p)
    print(f"{p.split('/')[-1]}: {len(u)} unresolved")
    for n,ls in sorted(u.items(), key=lambda x:-len(x[1]))[:15]:
        print(f"    {n:<26} {len(ls)}x  first L{ls[0]}")
