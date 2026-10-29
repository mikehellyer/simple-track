import re,struct,sys
d=open(sys.argv[1],'rb').read()
pt=rb'\x40\x00(?:\x01\x00\x00\x00\x00)?(....)(.{8})(.{8})'
rx=re.compile(rb'(?s)'+pt*4)
segs=[]
for m in rx.finditer(d):
    g=m.groups(); pts=[(struct.unpack('<d',g[i+1])[0],struct.unpack('<d',g[i+2])[0]) for i in range(0,12,3)]
    ids=[struct.unpack('<I',g[i])[0] for i in range(0,12,3)]
    if all(abs(c)<1e5 for p in pts for c in p) and ids==list(range(ids[0],ids[0]+4)):
        segs.append((m.start(),pts))
print(len(segs),'beziers')
for o,p in segs[:12]: print(hex(o),[(round(x,2),round(y,2)) for x,y in p])
import json; json.dump([p for o,p in segs],open(sys.argv[2],'w'))
