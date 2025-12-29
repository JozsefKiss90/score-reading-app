export class State {
  constructor(boot){
    this.boot = boot;
    this.pageIndex = 0;
    this.readySvg  = false;

    this.boxesByAbs   = {};  // abs -> {left,right,top,bottom}
    this.anchorsByAbs = {};  // abs -> [x...]
    this.orderAbs     = [];  // visible order

    this.queued = null;      // pending cursor params
    this.last   = {page:-1, abs:-1, t:0, x:0};
    this.lastHL = -1;

    this.beatVisible = false;
    this.beatDivs = [];      // overlay divs

    // --- Beat selector state -------------------------------------------

    // abs measure index -> Set(beatIdx)
    this.selBeats = new Map();

    // Selected SVG note ids (subset of visible notes in sidebar)
    this.selNoteIds = new Set();

    // midiPitch(int) -> Set(noteId)
    this.selNotesByMidi = new Map();

    // Currently pressed MIDI pitches
    this.midiDown = new Set();

    // midiPitch(int) -> Set(noteId) currently painted green
    this.midiActiveIdsByMidi = new Map();
  }
}
