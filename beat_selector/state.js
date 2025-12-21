export class State {
  constructor(boot){
    this.boot = boot;
    this.pageIndex = 0;
    this.readySvg  = false;

    this.boxesByAbs   = {};  // abs -> {l,r,t,b}
    this.anchorsByAbs = {};  // abs -> [x...]
    this.orderAbs     = [];  // visible order

    this.queued = null;      // pending cursor params
    this.last   = {page:-1, abs:-1, t:0, x:0};
    this.lastHL = -1;

    this.beatVisible = false;
    this.beatDivs = [];      // overlay divs
  }
}
