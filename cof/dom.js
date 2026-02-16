export const Dom = {
  pageObj: () => document.getElementById('page'),
  frame:   () => document.getElementById('frame'),
  hud:     () => document.getElementById('hud'),
  barHL:   () => document.getElementById('barHL'),
  cursor:  () => document.getElementById('cursor'),
  beatList:() => document.getElementById('beatList'),
  svgDoc:  () => {
    const o = Dom.pageObj();
    try { return o?.contentDocument || null; } catch { return null; }
  },

  // Backward compatible: Dom.keyboard() still returns #keyboard
  // New: Dom.keyboard('cofKeyboard') returns #cofKeyboard
  keyboard: (id = 'keyboard') => document.getElementById(id),

  svgRoot: () => Dom.svgDoc()?.querySelector('svg') || null,
};
