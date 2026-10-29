import re,sys,struct,collections
d=open(sys.argv[1],'rb').read()
c=collections.Counter(); first={}
for m in re.finditer(rb'([\x01-\x7f])\x00{7}([\x20-\x7e]+)',d):
    n=m.group(1)[0]; s=m.group(2)[:n]
    if len(s)==n:
        c[s]+=1; first.setdefault(s,m.start())
for s,k in sorted(c.items(),key=lambda x:first[x[0]]):
    print(f"{first[s]:#08x} {k:5} {s.decode()}")
