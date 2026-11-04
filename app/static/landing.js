"use strict";
(() => {
  const canvas=document.getElementById("evidenceField"),button=document.getElementById("motionToggle");
  if(!canvas||!button)return;
  const context=canvas.getContext("2d"),reduced=window.matchMedia("(prefers-reduced-motion: reduce)");
  if(!context){button.hidden=true;return;}
  let width=0,height=0,ratio=1,paused=reduced.matches,frame=0,last=0,time=0;
  const points=Array.from({length:128},(_,i)=>({phase:i*2.39996323,band:i%4,depth:(i%17)/17,offset:((i*37)%101)/101}));
  function resize(){width=innerWidth;height=innerHeight;ratio=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);context.setTransform(ratio,0,0,ratio,0,0);draw(time);}
  function draw(t){
    context.clearRect(0,0,width,height);
    const cx=width*(width<760?.8:.77),cy=height*.47,scale=Math.min(width,height)*.58;
    const glow=context.createRadialGradient(cx,cy,0,cx,cy,scale*1.45);glow.addColorStop(0,"rgba(192,217,140,.19)");glow.addColorStop(.6,"rgba(173,194,153,.07)");glow.addColorStop(1,"rgba(173,194,153,0)");context.fillStyle=glow;context.fillRect(0,0,width,height);
    context.lineWidth=.65;context.strokeStyle="rgba(75,110,71,.07)";
    for(let x=(t*3)%64;x<width;x+=64){context.beginPath();context.moveTo(x,0);context.lineTo(x,height);context.stroke();}
    for(let y=0;y<height;y+=64){context.beginPath();context.moveTo(0,y);context.lineTo(width,y);context.stroke();}
    for(let band=0;band<4;band++){
      const ordinate=x=>height*(.2+band*.18)+Math.sin(x/width*6.28+t*.16+band)*scale*.08;
      context.beginPath();for(let n=0;n<=80;n++){const x=n/80*width,y=ordinate(x);if(n===0)context.moveTo(x,y);else context.lineTo(x,y);}context.strokeStyle="rgba(72,112,67,.10)";context.lineWidth=.8;context.stroke();
      const x=((t*22+band*width/4)%(width+60))-30;context.beginPath();context.arc(x,ordinate(x),2.4,0,Math.PI*2);context.fillStyle="rgba(145,177,65,.52)";context.fill();
    }
    const projected=points.map((p,i)=>{const angle=p.phase+t*(.035+p.band*.006),r=scale*(.24+p.depth*.88),wave=Math.sin(angle*2+t*.19+p.band)*scale*.08;return{x:cx+Math.cos(angle)*(r+wave),y:cy+Math.sin(angle)*r*.59+Math.sin(t*.16+p.offset*7)*scale*.12,alpha:.15+p.depth*.28,size:i%13===0?3:1.1};});
    for(let b=0;b<4;b++){
      context.beginPath();for(let i=0;i<=120;i++){const a=i/120*Math.PI*2,wr=scale*(.34+b*.2)+Math.sin(a*3+t*.23+b)*scale*.035;const x=cx+Math.cos(a+t*.025)*wr,y=cy+Math.sin(a)*wr*.61+Math.cos(a*2+t*.17)*scale*.055;if(i===0)context.moveTo(x,y);else context.lineTo(x,y);}context.closePath();context.strokeStyle=`rgba(69,108,63,${.1+b*.025})`;context.lineWidth=.7;context.stroke();
    }
    projected.forEach((p,i)=>{for(let n=1;n<=2;n++){const q=projected[(i+n*17)%projected.length],distance=Math.hypot(p.x-q.x,p.y-q.y);if(distance<scale*.3){context.beginPath();context.moveTo(p.x,p.y);context.lineTo(q.x,q.y);context.strokeStyle=`rgba(69,108,63,${(1-distance/(scale*.3))*.13})`;context.lineWidth=.6;context.stroke();}}context.beginPath();context.arc(p.x,p.y,p.size,0,Math.PI*2);context.fillStyle=i%13===0?"rgba(157,189,68,.65)":`rgba(48,99,71,${p.alpha})`;context.fill();});
    // Decorative animation never represents actual agent or job progress.
    const sweep=(Math.sin(t*.1)*.5+.5)*width;const wash=context.createLinearGradient(sweep-100,0,sweep+100,0);wash.addColorStop(0,"rgba(211,233,164,0)");wash.addColorStop(.5,"rgba(211,233,164,.09)");wash.addColorStop(1,"rgba(211,233,164,0)");context.fillStyle=wash;context.fillRect(sweep-100,0,200,height);
  }
  function animate(timestamp){if(paused||document.hidden){frame=0;return;}if(timestamp-last>=32){time+=Math.min((timestamp-last)/1000,.06);last=timestamp;draw(time);}frame=requestAnimationFrame(animate);}
  function update(){document.body.classList.toggle("motion-paused",paused);button.setAttribute("aria-pressed",String(paused));button.setAttribute("aria-label",paused?"Play background animation":"Pause background animation");button.textContent=paused?"Play motion ▷":"Pause motion Ⅱ";if(paused){cancelAnimationFrame(frame);frame=0;draw(time);}else if(!frame){last=performance.now();frame=requestAnimationFrame(animate);}}
  button.addEventListener("click",()=>{paused=!paused;update();});
  reduced.addEventListener?.("change",()=>{paused=reduced.matches;update();});
  document.addEventListener("visibilitychange",()=>{if(document.hidden){cancelAnimationFrame(frame);frame=0;}else update();});
  window.addEventListener("resize",resize,{passive:true});resize();update();
})();
