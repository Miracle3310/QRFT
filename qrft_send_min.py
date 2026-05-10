import os,struct,sys,tkinter as t,zlib
W,H,M,R,D=260,120,6,5,32
C=W*H//8-D*R
def B(s,n):
 a=[]
 for c in s:
  for k in range(7,-1,-1):a+=[c>>k&1]
 return(a+[0]*n)[:n]
p=sys.argv[1]if len(sys.argv)>1 else"test.txt"
dt=float(sys.argv[2])if len(sys.argv)>2 else .8
lp=int(sys.argv[3])if len(sys.argv)>3 else 0
fd=open(p,"rb").read();nm=os.path.basename(p).encode();d=struct.pack(">H",len(nm))+nm+fd;fc=zlib.crc32(d)&0xffffffff;N=max(1,(len(d)+C-1)//C);F=[]
for i in range(N):
 q=d[i*C:(i+1)*C];h=struct.pack(">4sBBHHIHII8s",b"QF10",1,D,i,N,len(d),len(q),fc,zlib.crc32(q)&0xffffffff,b"\0"*8);F+=[B(h*R+q,W*H)]
r=t.Tk();r.attributes("-fullscreen",1);r.configure(bg="white");r.bind("<Escape>",lambda e:r.destroy())
sw,sh=r.winfo_screenwidth(),r.winfo_screenheight();tw,th=W+2*M,H+2*M;s=max(1,min(sw//tw,max(1,sh-120)//th));ox=(sw-tw*s)//2;oy=max(8,(sh-th*s)//2-36)
c=t.Canvas(r,width=sw,height=sh,bg="white",highlightthickness=0);c.pack();st=[0,0]
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
 c.create_text(sw//2,max(10,oy-34),fill="#444",font=("Arial",14),text="Frame %d/%d %dB c=%d"%(st[0]+1,N,len(fd),s))
 st[0]+=1
 if st[0]>=N:
  st[0]=0;st[1]+=1
  if lp and st[1]>=lp:r.destroy();return
 r.after(int(dt*1000),g)
g();r.mainloop()
