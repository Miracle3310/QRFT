import argparse,os,struct,tkinter as t,zlib
W,H,M,R,D=260,120,6,5,32
C=W*H//8-D*R
def B(s,n):
 a=[]
 for c in s:
  for k in range(7,-1,-1):a+=[c>>k&1]
 return(a+[0]*n)[:n]
ap=argparse.ArgumentParser()
ap.add_argument("file",nargs="?",default="test.txt")
ap.add_argument("--auto-advance",type=float,default=0.4,help="seconds between automatic frame advances")
ap.add_argument("--start-immediately",action="store_true",help="start automatic playback without waiting for a key")
ap.add_argument("--manual",action="store_true",help="disable automatic frame advances")
args=ap.parse_args()
if args.manual:args.auto_advance=0
p=args.file
fd=open(p,"rb").read();nm=os.path.basename(p).encode();d=struct.pack(">H",len(nm))+nm+fd;fc=zlib.crc32(d)&0xffffffff;N=max(1,(len(d)+C-1)//C);F=[]
for i in range(N):
 q=d[i*C:(i+1)*C];h=struct.pack(">4sBBHHIHII8s",b"QF10",1,D,i,N,len(d),len(q),fc,zlib.crc32(q)&0xffffffff,b"\0"*8);F+=[B(h*R+q,W*H)]
r=t.Tk();r.attributes("-fullscreen",1);r.configure(bg="white")
sw,sh=r.winfo_screenwidth(),r.winfo_screenheight();tw,th=W+2*M,H+2*M;s=max(1,min(sw//tw,max(1,sh-120)//th));ox=(sw-tw*s)//2;oy=max(8,(sh-th*s)//2-36)
c=t.Canvas(r,width=sw,height=sh,bg="white",highlightthickness=0);c.pack();st=[0];buf=[""];run=[False]
def x(a,b):c.create_rectangle(ox+a*s,oy+b*s,ox+(a+1)*s,oy+(b+1)*s,fill="black",outline="black")
def g():
 c.delete("all")
 for a in range(tw):
  x(a,0);x(a,1);x(a,th-2);x(a,th-1)
  if a%2<1:x(a,3)
 for b in range(th):
  x(0,b);x(1,b);x(tw-2,b);x(tw-1,b)
  if b%2<1:x(3,b)
 for a,b in((2,2),(tw-6,2),(2,th-6),(tw-6,th-6)):
  for yy in range(b,b+4):
   for xx in range(a,a+4):x(xx,yy)
 k=0
 for b in range(H):
  for a in range(W):
   if F[st[0]][k]:x(a+M,b+M)
   k+=1
 bw=min(260,tw*s);bx=(sw-bw)//2;c.create_rectangle(bx,max(0,oy-22),bx+bw,max(0,oy-16),fill="#ddd",outline="");c.create_rectangle(bx,max(0,oy-22),bx+int(bw*(st[0]+1)/N),max(0,oy-16),fill="#333",outline="")
 extra=(" goto "+buf[0])if buf[0]else""
 c.create_text(sw//2,max(10,oy-34),fill="#444",font=("Arial",14),text=("Frame %d/%d %dB c=%d"%(st[0]+1,N,len(fd),s))+extra)
def n(e=None):st[0]=(st[0]+1)%N;g()
def b(e=None):st[0]=(st[0]-1)%N;g()
def auto():
 if not run[0]:return
 n()
 r.after(max(1,int(args.auto_advance*1000)),auto)
def start():
 if args.auto_advance>0 and not run[0]:
  run[0]=True
  r.after(max(1,int(args.auto_advance*1000)),auto)
def key(e):
 ch=getattr(e,"char","");ks=getattr(e,"keysym","")
 if ch and ch.isdigit():buf[0]=(buf[0]+ch)[-6:];g();return
 if ks and (ks.isdigit() or (ks.startswith("KP_") and ks[3:].isdigit()) or (ks.startswith("Digit") and ks[5:].isdigit())):
  d=ks if ks.isdigit()else(ks[3:]if ks.startswith("KP_")else ks[5:])
  buf[0]=(buf[0]+d)[-6:];g();return
 if e.keysym in("Return","KP_Enter"):
  if buf[0]:
   v=int(buf[0]);buf[0]=""
   if 1<=v<=N:st[0]=v-1
   g()
  else:n();start()
 elif e.keysym in("space","Right")or ch=="n":n();start()
 elif e.keysym in("Left","BackSpace")or ch=="p":
  if buf[0]and e.keysym=="BackSpace":buf[0]=buf[0][:-1];g()
  else:b()
r.bind("<Escape>",lambda e:r.destroy())
r.bind("<Key>",key)
g()
if args.start_immediately:start()
r.mainloop()
