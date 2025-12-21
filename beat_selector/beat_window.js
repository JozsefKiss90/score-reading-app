window.BeatUI = (function () {
  // internal state + helpers

function setPageAndSvg(pageIndex, svgUrl) {
  window.BeatUI.setPageAndSvg(pageIndex, svgUrl);
}
function setBeatBoxesVisible(on) {
  window.BeatUI.setBeatBoxesVisible(on);
}
function jsSetCursorAbs(absIdx, tInMeasure, dur) {
  window.BeatUI.jsSetCursorAbs(absIdx, tInMeasure, dur);
}

  function init() { ... }

  init();

  return {
    setPageAndSvg,
    setBeatBoxesVisible,
    jsSetCursorAbs,
    rebuildSidebar,   // optional, but nice to expose
  };

  
})();
