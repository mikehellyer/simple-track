import struct, sys, lz4.block
d=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',d[4:8])[0]; p=12; ents={}
for _ in range(n):
    e=d.index(b'\0',p); nm=d[p:e].decode(); p=e+1
    off,sz,c=struct.unpack('<III',d[p:p+12]); p+=12; ents[nm]=(off,sz)
def get(nm):
    off,sz=ents[nm]; out=b''; q=off
    while len(out)<sz:
        u,pk=struct.unpack('<HH',d[q:q+4]); q+=4
        out+=lz4.block.decompress(d[q:q+pk],uncompressed_size=u); q+=pk
    return out
if sys.argv[2]=='ls':
    for k in ents:
        if sys.argv[3] in k: print(k)
else: sys.stdout.buffer.write(get(sys.argv[2]))
