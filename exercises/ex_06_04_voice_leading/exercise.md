# Lecke 6.4 – Hangvezetés és feloldási minták
## Kommentált gyakorlat – a sequences.json taskjaihoz

Ebben a leckében **nem az akkordváltás a tananyag**,  
hanem az, hogy **mely hangok mozognak szükségszerűen**,  
és melyek maradnak invariánsak.

Az alábbi feladatok mindegyike
**klasszikus hangvezetési alapeset**.

---

## Task t1 – Domináns → tonika (V7 → I)

**Akkordok:**
- G–B–D–F → C–E–G  
- (domináns szeptim → dúr triád)

### Mit kell felismerned?
- **B** = vezetőhang → **C** (félhang felfelé)
- **F** = szeptim → **E** (lépés lefelé)
- **D** = közös hang → **marad**
- **G (basszus)** → **C** (kvintlépés, funkcionális tengely)

### Elméleti kapcsolat
Ez a *tankönyvi hangvezetés*, mert:
- két **vezetett hang** oldódik,
- a többi hang **minimálisan mozog**.

Ha ezt nem látod előre,
akkor az akkordváltás mindig „meglepetés”.

---

## Task t2 – Vezetőhang-feloldás (V7 → I, más hangnemben)

**Akkordok:**
- D–F#–A–C → G–B–D

### Mit kell felismerned?
- **F#** → **G** (vezetőhang)
- **C** → **B** (szeptim lefelé)
- **A** → **G** (lépés)
- **D** = közös hang

### Elméleti kapcsolat
Ez megerősíti:
- a vezetőhang **nem hangnemfüggő**,
- hanem **strukturális szerep**.

A hangvezetési kényszer
transzponálható, mert **nem konkrét hangokra**,  
hanem **intervallumokra** épül.

---

## Task t3 – Félszűk → domináns (iiø7 → V7 mollban)

**Akkordok:**
- B–D–F–A → E–G#–B–D

### Mit kell felismerned?
- **B** → **B** (közös hang)
- **D** → **D** (közös hang)
- **F** → **E** (félhang lefelé)
- **A** → **G#** (félhang lefelé)
- basszus: **B → E** (funkcionális mozgás)

### Elméleti kapcsolat
Ez a példa mutatja, hogy:
- **nem minden hang vezetőhang**,
- de az instabil intervallumok **nem maradhatnak**.

A félszűk akkord:
- nem „állapot”,
- hanem **átmeneti szerkezet**.

---

## Task t4 – Teljesen szűkített → tonika

**Akkordok:**
- B–D–F–Ab → C–Eb–G

### Mit kell felismerned?
- **B** → **C** (vezetőhang)
- **D** → **Eb** (félhang felfelé)
- **F** → **G** (lépés)
- **Ab** → **G** (félhang lefelé)

### Elméleti kapcsolat
Ez a **maximális feszültség → nyugalom** modellje.

A teljesen szűkített szeptim:
- szimmetrikus,
- több irányba oldható,
de **mindig**:
- kis lépésekben,
- a legközelebbi stabil hangokra.

---

## Összefoglaló olvasási kulcs

Ha egy akkordváltást látsz, kérdezd meg:

1. Mely hangok **félhangra vannak** egy stabil hangtól?
2. Mely hangok **közösek**?
3. Mely hangok **nem maradhatnak ott**, ahol vannak?

Ha ezekre tudsz válaszolni,
a váltás **előre olvasható**.

Ez a hangvezetés gyakorlati értelme.
