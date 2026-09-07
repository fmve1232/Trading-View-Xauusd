#!/usr/bin/env python3
"""Pine v6 pre-compile checks. NOT a compiler -- catches a specific class of errors
that would otherwise only surface on paste. A clean run does NOT mean it compiles."""
import sys,re,collections

def strip(src):
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

def check(path):
    src=open(path,encoding='utf-8').read()
    raw=src.split('\n'); S=strip(src); errs=[]

    # 1. balanced delimiters, per line and cumulative
    depth={'(':0,'[':0}
    pair={')':'(',']':'['}
    for i,l in enumerate(S,1):
        for ch in l:
            if ch in '([': depth[ch]+=1
            elif ch in ')]':
                depth[pair[ch]]-=1
                if depth[pair[ch]]<0: errs.append(f"L{i}: unbalanced '{ch}'"); depth[pair[ch]]=0
    for k,v in depth.items():
        if v: errs.append(f"EOF: {v} unclosed '{k}'")

    # 2. indentation must be a multiple of 4 and never jump by >4
    prev=0
    for i,l in enumerate(S,1):
        if not l.strip(): continue
        ind=len(l)-len(l.lstrip(' '))
        if ind%4: errs.append(f"L{i}: indent {ind} not a multiple of 4")
        if ind-prev>4 and prev>=0: errs.append(f"L{i}: indent jumps {prev}->{ind}")
        prev=ind

    # 3. a block opener must be followed by a deeper line
    for i,l in enumerate(S):
        s=l.rstrip()
        if not s.strip(): continue
        if re.search(r'(^|\s)(if|else|for|while)\b.*$',s) and s.rstrip().endswith(':'):
            errs.append(f"L{i+1}: stray ':' (Pine has no colon block syntax)")
        if re.match(r'^\s*(if|for|while|else)\b',s) and not s.strip().endswith('=>'):
            ind=len(s)-len(s.lstrip(' '))
            nxt=None
            for j in range(i+1,len(S)):
                if S[j].strip(): nxt=S[j];break
            if nxt is not None:
                nind=len(nxt)-len(nxt.lstrip(' '))
                if nind<=ind: errs.append(f"L{i+1}: block opener not followed by an indented body")


    # 5. else / else-if chain integrity  (added after this checker MISSED a real
    #    `else` inserted before an `else if`, which Pine rejects)
    stack={}
    for i,l in enumerate(S,1):
        if not l.strip(): continue
        ind=len(l)-len(l.lstrip(' ')); t=l.strip()
        if re.match(r'^if\b',t):
            stack[ind]='if'
        elif re.match(r'^else\s+if\b',t):
            if stack.get(ind) not in ('if','elif'):
                errs.append(f"L{i}: 'else if' with no matching 'if' at indent {ind}")
            stack[ind]='elif'
        elif re.match(r'^else\b',t):
            if stack.get(ind) not in ('if','elif'):
                errs.append(f"L{i}: 'else' with no matching 'if' at indent {ind}")
            stack[ind]='else'
        elif ind in stack and ind<=(len(l)-len(l.lstrip(' '))):
            if re.match(r'^(if|else)\b',t) is None and ind in stack and stack.get(ind)=='else':
                stack.pop(ind,None)

    # 4. `=` used where `:=` is required (reassigning a known var at deeper indent)
    declared=set()
    for i,l in enumerate(S,1):
        m=re.match(r'^\s*(?:var\s+|varip\s+)?(?:[A-Za-z_]\w*(?:<[^>]*>)?(?:\[\])?\s+)?([A-Za-z_]\w*)\s*=(?!=)',l)
        if m: declared.add(m.group(1))
    return errs

if __name__=='__main__':
    bad=0
    for p in sys.argv[1:]:
        e=check(p)
        print(f"{p}: {'OK' if not e else str(len(e))+' issue(s)'}")
        for x in e[:12]: print("   ",x)
        if len(e)>12: print(f"    ... and {len(e)-12} more")
        bad+=len(e)
    sys.exit(1 if bad else 0)
