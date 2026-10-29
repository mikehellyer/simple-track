import struct, sys
f=open(sys.argv[1],'rb'); d=f.read()
magic=d[:4]; n,chk=struct.unpack('<II',d[4:12]); p=12; ents=[]
for _ in range(n):
    e=d.index(b'\0',p); name=d[p:e].decode('utf-8','replace'); p=e+1
    off,sz,c=struct.unpack('<III',d[p:p+12]); p+=12; ents.append((name,off,sz))
print(magic,n,'entries')
import collections
top=collections.Counter()
ext=collections.Counter()
for nm,o,s in ents:
    parts=nm.split('/'); top['/'.join(parts[:2]) if parts[0] in('Data','Libraries') else parts[0]]+=1
    ext[nm.rsplit('.',1)[-1]]+=1
print(top.most_common(40)); print(ext.most_common(30))
if len(sys.argv)>2:
    for nm,o,s in ents:
        if sys.argv[2] in nm: print(s,nm)
