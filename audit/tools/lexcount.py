import re,sys
TOK=re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_][A-Za-z0-9_.]*|\d+\.?\d*(?:e[-+]?\d+)?|:=|==|!=|<=|>=|=>|\+=|-=|\*=|/=|\S')
def toks(line):
    # drop // comments outside strings
    out=[];i=0
    for m in TOK.finditer(line):
        t=m.group(0)
        if t=='/' and line[m.start():m.start()+2]=='//': break
        out.append(t)
    return out
def count(path,a=1,b=None):
    L=open(path,encoding='utf-8').read().split('\n')
    b=b or len(L)
    return sum(len(toks(l)) for l in L[a-1:b])
if __name__=='__main__':
    p=sys.argv[1]; a=int(sys.argv[2]) if len(sys.argv)>2 else 1; b=int(sys.argv[3]) if len(sys.argv)>3 else None
    print(count(p,a,b))
