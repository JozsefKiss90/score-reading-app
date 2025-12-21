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
  svgRoot: () => Dom.svgDoc()?.querySelector('svg') || null,
};
