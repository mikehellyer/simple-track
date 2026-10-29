import re,struct,math,sys
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
d=open(sys.argv[1],'rb').read()
def bez(p,n=30):
    return [tuple(sum(c*q[k] for c,q in zip(((1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3),p)) for k in (0,1)) for t in [i/n for i in range(n+1)]]
# flex beziers
pt=rb'\x40\x00(?:\x01\x00\x00\x00\x00)?(....)(.{8})(.{8})'
flex=[]
for m in re.finditer(rb'(?s)'+pt*4,d):
    g=m.groups(); flex.append([struct.unpack('<2d',g[i+1]+g[i+2]) for i in range(0,12,3)])
lib=sys.argv[3].encode()
eps=[]
for m in re.finditer(bytes([len(lib)])+b'\x00'*7+lib,d):
    s=m.start(); x,y,z,a=struct.unpack('<4d',d[s-32:s])
    if abs(x)<1e5 and abs(y)<1e5 and (x,y)!=(0,0) and -7<a<7: eps.append((s,x,y,a))
ci=d.find(b'\x05'+b'\x00'*7+b'CPart'); cid=d[ci-2:ci]
starts=[ci]+[m.start() for m in re.finditer(rb'\x01\x01'+re.escape(cid),d)]
fig,ax=plt.subplots(figsize=(16,4))
for f in flex: xs,ys=zip(*bez(f)); ax.plot(xs,ys,'b-',lw=2)
groups={}
import bisect
for e in eps:
    i=bisect.bisect(starts,e[0])-1; groups.setdefault(i,[]).append(e)
for g in groups.values():
    if len(g)<2: continue
    s=g[0]
    for e in g[1:]:
        L=math.dist(s[1:3],e[1:3])/3
        p=[s[1:3],(s[1]+L*math.sin(s[3]),s[2]+L*math.cos(s[3])),(e[1]+L*math.sin(e[3]),e[2]+L*math.cos(e[3])),e[1:3]]
        xs,ys=zip(*bez(p)); ax.plot(xs,ys,'r-',lw=2)
for e in eps: ax.plot(e[1],e[2],'k.',ms=4)
ax.set_aspect('equal'); ax.invert_yaxis(); ax.grid(alpha=.3); fig.savefig(sys.argv[2],dpi=90,bbox_inches='tight')
print(len(flex),'flex',sum(len(g)>=2 for g in groups.values()),'turnouts')
