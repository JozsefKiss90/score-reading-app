import math, wave, struct, sys

SAMPLE_RATE = 44100
DURATION_SEC = 60.0
BPM = 52
BEAT = 60.0 / BPM  # egy negyed hossza másodpercben
MASTER_GAIN = 0.9  # kimeneti jelszint limit

# Egyszerű "zongora-szerű" hang: pár felhang + gyors lecsengés
def piano_tone(freq, t, dur):
    # Amplitúdó boríték (ADSR-szerű, nagyon egyszerű)
    a = 0.008    # attack s
    d = 0.20     # decay s
    s = 0.25     # sustain szint
    r = 0.35     # release s
    # Boríték görbe
    if t < 0 or t > dur:
        env = 0.0
    elif t < a:
        env = t / a
    elif t < a + d:
        env = 1.0 - (1.0 - s) * ((t - a) / d)
    elif t < max(dur - r, a + d):  # sustain fázis
        env = s
    else:  # release
        tr = max(0.0, t - (dur - r))
        env = s * max(0.0, 1.0 - tr / r)

    # Enyhe "melegség": kicsi felhangok + nagyon kis detune
    det = freq * 0.003
    f1 = 2 * math.pi * (freq - det) * t
    f2 = 2 * math.pi * (freq + det) * t
    f3 = 2 * math.pi * (2.0 * freq) * t     # 2. felhang
    f4 = 2 * math.pi * (3.0 * freq) * t     # 3. felhang

    # Súlyozott additív szintézis (lágy, nem harsány)
    s0 = 0.68 * math.sin(f1) + 0.68 * math.sin(f2)
    s1 = 0.22 * math.sin(f3)
    s2 = 0.10 * math.sin(f4)

    return env * (s0 + s1 + s2) * 0.6

# Hasznos: hangnév -> frekvencia (A4=440)
NOTE_MAP = {'C':0,'C#':1,'Db':1,'D':2,'D#':3,'Eb':3,'E':4,'F':5,'F#':6,'Gb':6,'G':7,'G#':8,'Ab':8,'A':9,'A#':10,'Bb':10,'B':11}
def hz(note):
    # pl. "D2", "Bb1", "A3"
    name = note[:-1]
    octv = int(note[-1])
    n = NOTE_MAP[name] + (octv + 1) * 12
    return 440.0 * (2 ** ((n - 69) / 12.0))

# Egyszerű NoteEvent
class Note:
    def __init__(self, start, dur, freq, vel=1.0):
        self.start = start
        self.dur = dur
        self.freq = freq
        self.vel = max(0.0, min(1.0, vel))

# Szólamok felépítése (mély tartomány, kerüljük a magas csilingelést)
notes_bass = []   # bal kéz, lassú alapok
notes_mid  = []   # közép szólam, bontott akkordok
notes_mel  = []   # jobb kéz, lírai, de nem megy magasra

# Szerkezet: 3×20 mp
# 0–20 mp: Dm – Bb – Gm – A
# 20–40 mp: Dm – Gm – A – Dm
# 40–60 mp: visszatérés Dm, hosszú búcsú

# Időképletek
sec = 0.0

# Segédfüggvények szólamokhoz
def add_bass(root_note, length_sec):
    # Gyök hang + kvint felütés a takton belül
    r = hz(root_note)
    fifth = r * 1.5
    notes_bass.append(Note(sec, length_sec * 0.66, r, 0.85))
    notes_bass.append(Note(sec + length_sec * 0.50, length_sec * 0.5, fifth, 0.55))

def add_mid_triad(root, third, fifth, length_sec):
    # Bontott triád belül csendekkel
    step = length_sec / 4.0
    notes_mid.append(Note(sec + 0.00*step, step*1.5, hz(root), 0.55))
    notes_mid.append(Note(sec + 1.50*step, step*1.0, hz(third), 0.50))
    notes_mid.append(Note(sec + 2.50*step, step*1.5, hz(fifth), 0.50))

def add_melody(pitches, total_len):
    # Egyszerű dallam-motívum, nem magas, kvázi "sóhaj"
    seg = total_len / len(pitches)
    for i, nname in enumerate(pitches):
        dur = seg * 0.85
        start = sec + i * seg
        notes_mel.append(Note(start, dur, hz(nname), 0.45))

# I. szakasz (0–20 s): Dm, Bb, Gm, A
for chord_name, bass, triad, mel in [
    ("Dm", "D2", ("D3","F3","A3"), ("F3","E3","D3","C3")),
    ("Bb", "Bb1", ("Bb2","D3","F3"), ("D3","C3","Bb2")),
    ("Gm", "G1", ("G2","Bb2","D3"), ("Bb2","A2","G2")),
    ("A", "A1", ("A2","C#3","E3"), ("C#3","B2","A2")),
]:
    length = 20.0/4
    add_bass(bass, length)
    add_mid_triad(*triad, length)
    add_melody(mel, length)
    sec += length

# II. szakasz (20–40 s): Dm, Gm, A, Dm
for chord_name, bass, triad, mel in [
    ("Dm", "D2", ("D3","F3","A3"), ("F3","E3","D3")),
    ("Gm", "G1", ("G2","Bb2","D3"), ("Bb2","A2","G2")),
    ("A",  "A1", ("A2","C#3","E3"), ("C#3","B2","A2")),
    ("Dm", "D2", ("D3","F3","A3"), ("F3","E3","D3")),
]:
    length = 20.0/4
    add_bass(bass, length)
    add_mid_triad(*triad, length)
    add_melody(mel, length)
    sec += length

# III. szakasz (40–60 s): vissza Dm, búcsú – hosszan kitartott zárás
# 40–52 s: két félperiódus lassú lebegés
for _ in range(2):
    length = 6.0
    add_bass("D2", length)
    add_mid_triad("D3","F3","A3", length)
    add_melody(("F3","E3","D3"), length)
    sec += length

# 52–60 s: végső akkord (Dm add9: D–E–A mélyen), hosszú lecsengéssel
final_len = 8.0
notes_bass.append(Note(sec, final_len, hz("D2"), 0.9))
notes_mid.append(Note(sec, final_len, hz("A2"), 0.65))
notes_mel.append(Note(sec, final_len, hz("E3"), 0.55))
# kész az ütemezés

# Renderelés
total_samples = int(DURATION_SEC * SAMPLE_RATE)
buf = [0.0] * total_samples

def add_note_to_buffer(note_obj):
    start_idx = int(note_obj.start * SAMPLE_RATE)
    end_idx = min(total_samples, int((note_obj.start + note_obj.dur) * SAMPLE_RATE))
    if end_idx <= start_idx: 
        return
    for i in range(start_idx, end_idx):
        t = i / SAMPLE_RATE - note_obj.start
        buf[i] += note_obj.vel * piano_tone(note_obj.freq, t, note_obj.dur)

for n in notes_bass + notes_mid + notes_mel:
    add_note_to_buffer(n)

# Normalizálás
peak = max(1e-9, max(abs(x) for x in buf))
norm = MASTER_GAIN / peak
buf = [x * norm for x in buf]

# WAV írás 16-bit PCM
out_name = "Zsambeki_alkony_Bucsu.wav"
with wave.open(out_name, "w") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SAMPLE_RATE)
    for x in buf:
        val = max(-1.0, min(1.0, x))
        w.writeframes(struct.pack('<h', int(val * 32767)))

print(f"Kész: {out_name}")