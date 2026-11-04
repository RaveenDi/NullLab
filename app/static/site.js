"use strict";
(() => {
  document.querySelectorAll(".site-header").forEach(header => {
    const toggle=header.querySelector(".site-menu"), nav=header.querySelector(".site-nav");
    if(!toggle||!nav)return;
    function setMenu(open,restore=false){header.dataset.menuOpen=String(open);toggle.setAttribute("aria-expanded",String(open));toggle.setAttribute("aria-label",open?"Close navigation":"Open navigation");if(restore)toggle.focus();}
    toggle.addEventListener("click",()=>setMenu(header.dataset.menuOpen!=="true"));
    nav.querySelectorAll("a").forEach(link=>link.addEventListener("click",()=>setMenu(false)));
    document.addEventListener("keydown",event=>{if(event.key==="Escape"&&header.dataset.menuOpen==="true")setMenu(false,true);});
    document.addEventListener("pointerdown",event=>{if(header.dataset.menuOpen==="true"&&!header.contains(event.target))setMenu(false);});
  });
})();
