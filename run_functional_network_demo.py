"""Functional Degree Network -- staged journey launcher.

Run::

    .venv/Scripts/python.exe run_functional_network_demo.py            # major
    .venv/Scripts/python.exe run_functional_network_demo.py --minor    # minor
    .venv/Scripts/python.exe run_functional_network_demo.py --template <id>

A practice-first harmonic network over a few major journey keys (C, G, D, F)
-- or, with ``--minor``, the v2 minor journey (A, E, D, B: harmonic-minor
chords, the real minor V, ticket 15 / G2c) --
in which **every diatonic degree is a real graph node**, the graph reveals
itself in guided stages, and *playing the trainer is what drives the graph*:

  * **Top strip (Qt):** the stage bar -- title + explanation, ``◀ Stage`` /
    ``Stage ▶`` buttons (Next stays disabled until the stage's drill(s) are
    finished) and a "nodes lit" progress label.
  * **Left:** the network web UI (``beat_selector/harmonic_network.html``,
    rendered unmodified -- the payload shares the ``harmony-network/v1``
    schema), initialised ONCE with the full multi-key payload; stages are a
    visibility whitelist (``setVisibleNodes``) + relation filters, so
    transitions feel animated rather than reloaded.
  * **Right:** an embedded **Harmony Trainer** (``HarmonyTrainerWindow``)
    whose dropdown groups are the journey stages.  Every 400 ms the host
    reads the live target chord and lights the **exact degree node** being
    exercised (node ids encode key+degree -- no pitch-class guessing); each
    correctly played chord permanently lights its node, and finishing a
    stage's drill(s) unlocks the next stage.

Progress (stages, drills, lit nodes) persists between sessions via
``harmony.functional_journey.JourneyProgress`` in
``.functional_network_progress.json``.  The existing Harmonic Network /
Atlas / Circle / Trainer / Lab / Curriculum launchers are untouched.
"""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from datetime import datetime
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QCoreApplication, QTimer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSplitter,
)

from theory.diatonic_harmony import parse_key
from harmony.exercise_spec import HarmonyExerciseSpec, compile_exercise
from harmony.functional_network import (
    build_functional_network,
    functional_payload,
    degree_node_id,
    panel_mode,
)
from harmony.functional_network_template import get_template
from harmony.functional_journey import (
    JourneyStage,
    journey_stages,
    drill_node_ids,
    DEFAULT_PROGRESS_FILENAME,
)
from harmony.progress_service import ProgressService
from run_harmonic_network_demo import HarmonicNetworkView
from run_harmony_trainer_demo import (
    HarmonyTrainerWindow, MidiService, ATLAS_GROUP,
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class FunctionalNetworkView(HarmonicNetworkView):
    """The shared network web UI plus the progressive-journey host hooks."""

    def set_visible_nodes(self, ids: Optional[List[str]]):
        self._run_js(
            "window.HarmonicNetwork && "
            "window.HarmonicNetwork.setVisibleNodes(%s);" % json.dumps(ids))

    def set_relations(self, relations_on: List[str],
                      all_relations: List[str]):
        rel = {r: (r in relations_on) for r in all_relations}
        self._run_js(
            "window.HarmonicNetwork && window.HarmonicNetwork.setFilter(%s);"
            % json.dumps({"relations": rel}))

    def select_node(self, node_id: str):
        self._run_js(
            "window.HarmonicNetwork && "
            "window.HarmonicNetwork.selectNode(%s);" % json.dumps(node_id))

    def mark_completed(self, ids: List[str]):
        if ids:
            self._run_js(
                "window.HarmonicNetwork && "
                "window.HarmonicNetwork.markCompleted(%s);"
                % json.dumps(list(ids)))

    def highlight_degree(self, target: dict):
        if self._ready and target:
            self._run_js(
                "window.HarmonicNetwork && "
                "window.HarmonicNetwork.highlightFromDegreeTarget(%s);"
                % json.dumps(target))


class FunctionalNetworkWindow(QWidget):
    """Stage bar (top) + network web UI (left) + Harmony Trainer (right)."""

    #: Drills this network never makes launchable (defence-in-depth; every
    #: node here is triad-based and launchable, but keep the guard anyway).
    _RESERVED_DRILLS = {"seventh_chord"}

    def __init__(self, midi_service=None, template_id: Optional[str] = None,
                 progress_path=DEFAULT_PROGRESS_FILENAME):
        super().__init__()

        template = get_template(template_id)
        self.setWindowTitle(f"Functional Degree Network — "
                            f"{'minor' if template.mode == 'minor' else 'staged'} "
                            f"journey")
        self._network = build_functional_network(template)
        self._stages: List[JourneyStage] = journey_stages(self._network)
        # Journey progress routes through the unified service (ticket 08).
        self._progress = ProgressService(journey_path=progress_path).journey
        self._implemented = self._network.template.implemented_relations()
        self._node_ids = {n.id for n in self._network.nodes}
        self._degree_ids = {n.id for n in self._network.nodes
                            if n.kind == "degree_triad"}
        self._lit = {nid for nid in self._progress.lit_node_ids()
                     if nid in self._node_ids}

        # -- embedded trainer: one dropdown group per stage-with-drills ----
        groups: "OrderedDict[str, List[HarmonyExerciseSpec]]" = OrderedDict()
        for stage in self._stages:
            if stage.drills:
                groups[stage.title] = list(stage.drills)
        groups[ATLAS_GROUP] = []            # node-click launches land here
        self.trainer = HarmonyTrainerWindow(
            groups, midi_service=midi_service, with_circle=False)

        self.net_view = FunctionalNetworkView(
            functional_payload(self._network))
        self.net_view.launchRequested.connect(self._on_launch)

        # -- stage bar ------------------------------------------------------
        bar = QHBoxLayout()
        bar.setContentsMargins(8, 6, 8, 0)
        self.btnPrevStage = QPushButton("◀ Stage")
        self.btnPrevStage.clicked.connect(
            lambda: self._go_stage(self._stage_index - 1))
        bar.addWidget(self.btnPrevStage)
        self.lblStageTitle = QLabel("")
        self.lblStageTitle.setStyleSheet("font-weight:600;")
        bar.addWidget(self.lblStageTitle)
        bar.addStretch(1)
        self.lblLit = QLabel("")
        bar.addWidget(self.lblLit)
        self.btnNextStage = QPushButton("Stage ▶")
        self.btnNextStage.clicked.connect(
            lambda: self._go_stage(self._stage_index + 1))
        bar.addWidget(self.btnNextStage)

        self.lblExplanation = QLabel("")
        self.lblExplanation.setWordWrap(True)
        self.lblExplanation.setContentsMargins(8, 2, 8, 6)
        self.lblExplanation.setStyleSheet("color:#334155;")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.net_view)
        splitter.addWidget(self.trainer)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addLayout(bar)
        root.addWidget(self.lblExplanation)
        root.addWidget(splitter, 1)

        # -- runtime state ---------------------------------------------------
        self._stage_index = self._progress.resume_stage_index(self._stages)
        self._targets_cache: Dict[str, List[dict]] = {}
        self._last_target: Optional[dict] = None
        self._finish_handled = False
        # The drill actually on screen. Tracked explicitly (refreshed on every
        # poll while the trainer reports one) so a finish is never attributed
        # to the wrong spec: _current_trainer_spec() goes stale when the user
        # selects the empty "From Atlas" group, and an async state callback
        # can arrive just after a new drill loaded.
        self._active_spec: Optional[HarmonyExerciseSpec] = None
        #: Chord indexes of the active drill observed with ``completed`` true
        #: (i.e. actually played). Per-chord lighting requires this, so
        #: clicking through the trainer's chord cards lights nothing.
        self._completed_idx_seen: set = set()

        # Boot: wait for the web view, then apply persisted lit nodes + the
        # resume stage (the view sets _ready only after init() ran in JS).
        self._boot_timer = QTimer(self)
        self._boot_timer.setInterval(200)
        self._boot_timer.timeout.connect(self._try_boot)
        self._boot_timer.start()

        # Follow the trainer's current chord (exact-id degree highlight).
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(400)
        self._sync_timer.timeout.connect(self._poll_sync)
        self._sync_timer.start()

        # Watch for a finished drill (stage unlock + node lighting).
        self._state_timer = QTimer(self)
        self._state_timer.setInterval(400)
        self._state_timer.timeout.connect(self._poll_state)
        self._state_timer.start()

        self._refresh_stage_bar()

    # ------------------------------------------------------------------
    # boot / stage machine
    # ------------------------------------------------------------------
    def _try_boot(self):
        if not getattr(self.net_view, "_ready", False):
            return
        self._boot_timer.stop()
        self.net_view.mark_completed(sorted(self._lit))
        self._apply_stage(self._stage_index)

    def _go_stage(self, index: int):
        if not 0 <= index < len(self._stages):
            return
        self._apply_stage(index)

    def _apply_stage(self, index: int):
        index = max(0, min(index, len(self._stages) - 1))
        self._stage_index = index
        stage = self._stages[index]

        self.net_view.set_visible_nodes(stage.visible_node_ids)
        self.net_view.set_relations(stage.visible_relations,
                                    self._implemented)
        if stage.emphasis_node_ids:
            self.net_view.select_node(stage.emphasis_node_ids[0])

        self._progress.mark_stage_started(stage.stage_id, _now())
        self._load_stage_drill(stage)
        self._refresh_stage_bar()

    def _load_stage_drill(self, stage: JourneyStage):
        """Select the stage's trainer group (loads its first drill)."""
        if not stage.drills:
            return
        try:
            gi = self.trainer._group_names.index(stage.title)
        except ValueError:
            self.trainer.load_external_spec(stage.drills[0])
            return
        if self.trainer.cmbGroup.currentIndex() == gi:
            self.trainer._on_group_changed(gi)      # re-load the first drill
        else:
            self.trainer.cmbGroup.setCurrentIndex(gi)

    def _refresh_stage_bar(self):
        stage = self._stages[self._stage_index]
        done = self._progress.stage_satisfied(stage)
        self.lblStageTitle.setText(
            f"{stage.title}{' ✓' if done else ''}"
            f"   ({self._stage_index + 1}/{len(self._stages)})")
        self.lblExplanation.setText(stage.explanation)
        self.btnPrevStage.setEnabled(self._stage_index > 0)
        # Browsing is free (a locked journey reads as a broken app, especially
        # without a MIDI keyboard attached); the ✓ and the lit-node counter
        # still only reward actually finished drills.
        self.btnNextStage.setEnabled(self._stage_index < len(self._stages) - 1)
        lit = len(self._lit & self._degree_ids)
        self.lblLit.setText(f"Nodes lit: {lit}/{len(self._degree_ids)}")

    # ------------------------------------------------------------------
    # node-click -> trainer launch (identical pattern to the v1 demo)
    # ------------------------------------------------------------------
    def _on_launch(self, spec_dict: dict):
        if not isinstance(spec_dict, dict) or \
                spec_dict.get("drill") in self._RESERVED_DRILLS:
            print("[FNET] refusing reserved/invalid drill:",
                  (spec_dict or {}).get("drill"))
            return
        try:
            spec = HarmonyExerciseSpec.from_dict(spec_dict)
        except Exception as exc:
            print("[FNET] ignoring invalid spec:", exc)
            return
        self.trainer.load_external_spec(spec)

    # ------------------------------------------------------------------
    # trainer polling: exact-degree sync + per-chord lighting + unlock
    # ------------------------------------------------------------------
    def _current_trainer_spec(self) -> Optional[HarmonyExerciseSpec]:
        """The spec the trainer is showing right now (dropdown-aware)."""
        specs = getattr(self.trainer, "_specs", None)
        idx = getattr(self.trainer, "_current_idx", 0)
        if specs and 0 <= idx < len(specs):
            return specs[idx]
        return None

    def _refresh_active_spec(self) -> Optional[HarmonyExerciseSpec]:
        """Keep :attr:`_active_spec` pointed at the drill on screen.

        When the trainer's spec list goes empty (the "From Atlas" group) the
        score keeps showing the previous drill, so the last known spec stays
        active. A change of exercise resets the played-chord memory.
        """
        spec = self._current_trainer_spec()
        if spec is not None:
            if self._active_spec is None or \
                    spec.exercise_id != self._active_spec.exercise_id:
                self._completed_idx_seen = set()
                self._last_target = None
                self._active_spec = spec
                self._reveal_drill_nodes(spec)
            else:
                self._active_spec = spec
        return self._active_spec

    def _reveal_drill_nodes(self, spec: HarmonyExerciseSpec):
        """Union the stage whitelist with the active drill's nodes.

        Any exercise the user loads (a stage drill, a node click, another
        stage's group picked in the trainer dropdown) must relate visibly to
        the graph: if the current stage hides some of the drill's degree
        nodes, widen the whitelist so the drill's panel(s) are on screen.  A
        stage without a whitelist (free exploration) needs nothing.
        """
        stage = self._stages[self._stage_index]
        if stage.visible_node_ids is None:
            return
        try:
            extra = [nid for nid in drill_node_ids(spec)
                     if nid in self._node_ids]
        except Exception:
            return
        if not set(extra) - set(stage.visible_node_ids):
            return
        merged = list(dict.fromkeys(list(stage.visible_node_ids) + extra))
        self.net_view.set_visible_nodes(merged)

    def _targets_for(self, spec: HarmonyExerciseSpec) -> List[dict]:
        """Per-chord ``{key, degreeNumber}`` for a spec, via the same compiler
        the trainer uses (so the 'next chord' can never drift)."""
        if spec.exercise_id not in self._targets_cache:
            try:
                compiled = compile_exercise(spec)
                self._targets_cache[spec.exercise_id] = [
                    {"key": c.triad.key, "degreeNumber": c.triad.degree_number}
                    for c in compiled.chords]
            except Exception:
                self._targets_cache[spec.exercise_id] = []
        return self._targets_cache[spec.exercise_id]

    def _poll_sync(self):
        def on_target(target):
            if isinstance(target, dict) and target:
                self._handle_target(target)

        try:
            self.trainer.query_current_target(on_target)
        except Exception:
            pass

    def _handle_target(self, target: dict):
        # Enrich with the NEXT chord so the exercised resolves_to / prepares
        # edge lights up while the drill sits on the current chord.
        idx = target.get("absMeasure")
        spec = self._refresh_active_spec()
        if spec is not None and isinstance(idx, int):
            targets = self._targets_for(spec)
            if 0 <= idx + 1 < len(targets):
                nxt = targets[idx + 1]
                target = dict(target)
                target["nextKey"] = nxt["key"]
                target["nextDegreeNumber"] = nxt["degreeNumber"]
        self.net_view.highlight_degree(target)

        # Per-chord lighting: light the previous chord's node when the target
        # advanced one step past it AND we actually observed that chord fully
        # played (state().completed). The completed gate matters because the
        # trainer's chord cards / htNext also call goTo(): clicking through
        # the drill must light nothing. A chord whose completed window slips
        # between polls still lights when the drill finishes.
        last = self._last_target
        if last and isinstance(idx, int) and \
                idx == last.get("absMeasure", -99) + 1 and \
                last.get("absMeasure") in self._completed_idx_seen:
            self._light_target_node(last)
        self._last_target = target

    def _light_target_node(self, target: dict):
        # "A minor" targets light the m-suffixed minor panel node; the target
        # key alone carries the panel mode (harmonic minor is a scale form of
        # the same minor key, so its drills still report key "A minor").
        tonic, key_mode = parse_key(target.get("key") or "")
        num = target.get("degreeNumber")
        if tonic and isinstance(num, int) and num >= 1:
            self._mark_lit([degree_node_id(tonic, num - 1,
                                           panel_mode(key_mode))])

    def _mark_lit(self, node_ids: List[str]):
        new = [nid for nid in node_ids
               if nid in self._node_ids and nid not in self._lit]
        if not new:
            return
        ts = _now()
        for nid in new:
            self._lit.add(nid)
            self._progress.mark_node_lit(nid, ts)
        self.net_view.mark_completed(new)
        lit = len(self._lit & self._degree_ids)
        self.lblLit.setText(f"Nodes lit: {lit}/{len(self._degree_ids)}")

    def _poll_state(self):
        # Snapshot the on-screen spec NOW: the async callback below may fire
        # after the user already switched drills, and a finish must never be
        # credited to the newly loaded spec.
        active = self._refresh_active_spec()

        def on_state(state):
            if not isinstance(state, dict):
                return
            if state.get("completed") and isinstance(state.get("idx"), int):
                idx = state["idx"]
                self._completed_idx_seen.add(idx)
                # Light the chord's node the moment it is completed -- never
                # wait for the advance-past-it poll (a 400 ms window that an
                # auto-advancing trainer routinely skips straight past).
                if active is not None:
                    targets = self._targets_for(active)
                    if 0 <= idx < len(targets):
                        self._light_target_node(targets[idx])
            finished = bool(state.get("finished"))
            if finished and not self._finish_handled:
                self._finish_handled = True
                self._on_drill_finished(active)
            elif not finished:
                self._finish_handled = False

        try:
            self.trainer.query_trainer_state(on_state)
        except Exception:
            pass

    def _on_drill_finished(self, spec: Optional[HarmonyExerciseSpec]):
        if spec is None:
            return
        ts = _now()
        self._progress.mark_drill_finished(spec.exercise_id, ts)
        self._mark_lit(drill_node_ids(spec))
        stage = self._stages[self._stage_index]
        if self._progress.stage_satisfied(stage) and \
                not self._progress.stage_completed(stage.stage_id):
            self._progress.mark_stage_completed(stage.stage_id, ts)
        self._refresh_stage_bar()


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)

    # `--minor` launches the v2 minor journey (ticket 15 / G2c);
    # `--template <id>` any registered functional template.
    template_id: Optional[str] = None
    if "--minor" in argv:
        argv.remove("--minor")
        template_id = "functional_degree_network_minor_v2"
    if "--template" in argv:
        i = argv.index("--template")
        try:
            template_id = argv[i + 1]
        except IndexError:
            print("[FNET] --template needs a template id")
            return 2
        del argv[i:i + 2]

    QCoreApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication(argv)

    midi_service = None
    if MidiService is None:
        print("[FNET] MidiService import failed. MIDI will NOT work.")
    else:
        try:
            midi_service = MidiService()
            print("[FNET] MidiService active:",
                  getattr(midi_service, "port_name", None))
        except Exception as exc:
            print("[FNET] MidiService init failed:", exc)
            midi_service = None

    win = FunctionalNetworkWindow(midi_service=midi_service,
                                  template_id=template_id)
    win.resize(1720, 920)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
