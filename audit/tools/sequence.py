#!/usr/bin/env python3
"""Same-bar sequence screen (v26): a READ of a global that runs before a later WRITE of it
on the same bar sees an earlier stage (plain variable) or the previous bar (var).

Blocks are top-level statements in file order; a function's body counts at its first call
site. Reported: every read strictly between a symbol's first and last writer, tagged
DECISION when the reader lies in the backward slice of an alert/alertcondition/plot.
Most `var` hits are intended state machines (read last bar's state, then update it); each
hit is a question for a human, not a defect. Usage: python3 audit/tools/sequence.py FILE
"""
import os,re,sys,collections
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import trace as T
path=sys.argv[1]
raw=open(path,encoding='utf-8').read().split('\n')
S=T.strip('\n'.join(raw))
ID=re.compile(r'(?<![\w.])([A-Za-z_]\w*)(?![\w])')
FUNC=re.compile(r'^([A-Za-z_]\w*)\s*\(([^)]*)\)\s*=>')
# blocks
blocks=[]
cur=None
for i,l in enumerate(S,1):
    if not l.strip(): continue
    if not l.startswith(' '):
        cur=dict(a=i,b=i,lines=[i]); blocks.append(cur)
    else:
        if cur: cur['b']=i; cur['lines'].append(i)
DECL=re.compile(r'^\s*(?:var\s+|varip\s+)?(?:(?:float|int|bool|string|color|line|label|box|table|linefill|array<[^>]+>|matrix<[^>]+>|map<[^>]+>|\w+\[\])\s+)?([A-Za-z_]\w*)\s*(?::=|=(?!=)|\+=|-=|\*=|/=)')
TUP=re.compile(r'^\s*\[([^\]]+)\]\s*=')
glob=set()
for b in blocks:
    l=S[b['a']-1]
    m=FUNC.match(l)
    if m: b['w']={m.group(1)}; b['func']=m.group(1)
    else:
        w=set()
        mt=TUP.match(l)
        if mt: w|={x.strip().split()[-1] for x in mt.group(1).split(',')}
        else:
            md=DECL.match(l)
            if md: w.add(md.group(1))
        b['w']=w
    glob|=b['w']
# also := on globals inside indented lines
for b in blocks:
    for i in b['lines']:
        for m in re.finditer(r'(?<![\w.])([A-Za-z_]\w*)\s*(?::=|\+=|-=|\*=|/=)',S[i-1]):
            if m.group(1) in glob: b['w'].add(m.group(1))
        m=re.match(r'^\s*array\.(?:set|push|unshift|insert|clear|remove|shift|pop|fill)\(\s*([A-Za-z_]\w*)',S[i-1])
        for m in re.finditer(r'array\.(?:set|push|unshift|insert|clear|remove|shift|pop|fill)\(\s*([A-Za-z_]\w*)',S[i-1]):
            if m.group(1) in glob: b['w'].add(m.group(1))
for b in blocks:
    r=set()
    for i in b['lines']:
        r|={m.group(1) for m in ID.finditer(S[i-1])}
    b['r']=(r&glob)
writers=collections.defaultdict(list)
for k,b in enumerate(blocks):
    for w in b['w']: writers[w].append(k)
def back(seeds):
    seen=set(); st=list(seeds)
    while st:
        k=st.pop()
        if k in seen: continue
        seen.add(k)
        for s in blocks[k]['r']|blocks[k]['w']:
            for j in writers.get(s,[]):
                if j not in seen: st.append(j)
    return seen

funcs={b['func']:k for k,b in enumerate(blocks) if b.get('func')}
# effective execution position of each block: functions run at their first call site
callpos={}
for k,b in enumerate(blocks):
    if b.get('func'): continue
    for f in funcs:
        if f in b['r'] and f not in callpos: callpos[f]=k
# propagate nested calls
changed=True
while changed:
    changed=False
    for f,kf in funcs.items():
        for g in funcs:
            if g in blocks[kf]['r'] and f in callpos:
                p=callpos[f]
                if g not in callpos or callpos[g]>p: callpos[g]=p; changed=True
def pos(k):
    b=blocks[k]
    return callpos.get(b['func'],10**9) if b.get('func') else k
# decision closure
sink=[k for k,b in enumerate(blocks) if any(re.search(r'(?<![\w.])(alert|alertcondition|plot|plotshape)\s*\(',S[i-1]) for i in b['lines'])]
D=back(sink)
isvar=set()
for i,l in enumerate(S,1):
    m=re.match(r'^(?:var|varip)\s+(?:\S+\s+)?([A-Za-z_]\w*)\s*=',l)
    if m: isvar.add(m.group(1))
out=[]
for s_,ws in writers.items():
    # declaration = first writer; mutations = others
    wpos=sorted(pos(k) for k in ws)
    if len(wpos)<2: continue
    first,last=wpos[0],wpos[-1]
    for k,b in enumerate(blocks):
        if s_ in b['r'] and k not in ws:
            p=pos(k)
            if first<p<last:
                out.append((s_ in isvar, s_, blocks[k]['a'], blocks[[j for j in ws if pos(j)==last][0]]['a'], k in D))
for o in sorted(set(out),key=lambda x:(not x[4],x[1])): print(('VAR ' if o[0] else 'PLAIN'), o[1], 'read@L%d before last write@L%d'%(o[2],o[3]), 'DECISION' if o[4] else 'display')
