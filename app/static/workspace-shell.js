"use strict";
(() => {
  const $ = id => document.getElementById(id), workspace = $("workspace");
  let menuOpen = false, focused = false, nativeFullscreen = false, transitioning = false;
  let previousFocus = null, previousScroll = 0, inertBackground = [];

  function setMenu(open, restoreFocus = false) {
    menuOpen = open;
    $("mainHeader").setAttribute("data-menu-open", String(open));
    $("menuToggle").setAttribute("aria-expanded", String(open));
    $("menuToggle").setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    if (restoreFocus) $("menuToggle").focus();
  }

  function updateFocusLabel() {
    $("fullscreenButton").setAttribute("aria-pressed", String(focused));
    $("fullscreenButton").setAttribute("aria-label", focused ? "Exit focused author workspace" : "Expand author workspace");
    $("fullscreenLabel").textContent = focused ? nativeFullscreen ? "Exit fullscreen" : "Exit focus" : "Fullscreen";
  }

  function setFocused(active) {
    if (active === focused) return;
    if (active) {
      previousFocus = document.activeElement;
      previousScroll = window.scrollY || 0;
      inertBackground = [...document.querySelectorAll(".topbar, main > section:not(#workspace), footer, .skip")].map(node => [node, node.inert]);
      inertBackground.forEach(([node]) => { node.inert = true; });
      workspace.setAttribute("role", "dialog");
      workspace.setAttribute("aria-modal", "true");
      setMenu(false);
    } else {
      inertBackground.forEach(([node, prior]) => { node.inert = prior; });
      inertBackground = [];
      workspace.removeAttribute("role");
      workspace.removeAttribute("aria-modal");
    }
    focused = active;
    workspace.classList.toggle("is-focused", active);
    workspace.setAttribute("data-focus", String(active));
    document.body.classList.toggle("workspace-focused", active);
    document.documentElement?.classList.toggle("workspace-focused", active);
    updateFocusLabel();
    if (!active) {
      window.scrollTo?.({top: previousScroll, behavior: "instant"});
      previousFocus?.focus({preventScroll: true});
    }
  }

  async function leaveFocus() {
    try {
      if (document.fullscreenElement === workspace && document.exitFullscreen) await document.exitFullscreen();
    } catch {
      if (document.fullscreenElement === workspace) {
        nativeFullscreen = true;
        updateFocusLabel();
        return;
      }
    }
    nativeFullscreen = false;
    setFocused(false);
  }

  $("fullscreenButton").addEventListener("click", async () => {
    if (transitioning) return;
    transitioning = true;
    $("fullscreenButton").disabled = true;
    try {
      if (focused) await leaveFocus();
      else {
        setFocused(true);
        if (workspace.requestFullscreen) {
          try {
            await workspace.requestFullscreen();
            nativeFullscreen = document.fullscreenElement === workspace;
          } catch {
            // The viewport focus view also works when fullscreen is unsupported
            // or denied, including on mobile browsers and embedded previews.
            nativeFullscreen = false;
          }
        }
        updateFocusLabel();
        $("fullscreenButton").focus({preventScroll: true});
      }
    } finally {
      transitioning = false;
      $("fullscreenButton").disabled = false;
    }
  });

  $("menuToggle").addEventListener("click", () => setMenu(!menuOpen));
  ["brandHome", "workspaceNav", "historyNav", "methodNav", "scopeNav"].forEach(id => $(id).addEventListener("click", () => setMenu(false)));
  document.addEventListener?.("pointerdown", event => {
    if (menuOpen && !$("mainHeader").contains(event.target)) setMenu(false);
  });
  document.addEventListener?.("fullscreenchange", () => {
    if (document.fullscreenElement === workspace) {
      nativeFullscreen = true;
      setFocused(true);
      updateFocusLabel();
    } else if (nativeFullscreen) {
      nativeFullscreen = false;
      setFocused(false);
    }
  });
  document.addEventListener?.("keydown", event => {
    if (event.key === "Escape") {
      if (menuOpen) setMenu(false, true);
      if (focused) leaveFocus().catch(() => setFocused(false));
    }
    if (event.key === "Tab" && focused) {
      const targets = [...(workspace.querySelectorAll?.("a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex='0']") || [])].filter(node => node.getClientRects().length);
      const first = targets[0], last = targets[targets.length - 1];
      if (first && event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (last && !event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
})();
