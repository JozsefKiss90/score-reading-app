
from __future__ import annotations
import xml.etree.ElementTree as ET
from typing import Iterable, Dict, Any

def _iter_svg_note_like(root: ET.Element):
    for el in root.iter():
        tag = el.tag.split('}')[-1]
        if tag != 'g':
            continue
        cls = el.attrib.get('class', '')
        typ = el.attrib.get('data-vrv-type') or el.attrib.get('data-type') or ''
        if 'note' in cls or typ == 'note':
            yield el

def _attrs(el: ET.Element):
    keys = ('pname','accid','oct','midi','data-pname','data-accid','data-oct','data-midi','class','data-vrv-type','data-type')
    return {k: el.attrib.get(k) for k in keys if (k in el.attrib)}

def debug_svg_pitch_attrs(svg: str) -> str:
    try:
        root = ET.fromstring(svg)
    except Exception as e:
        return f"[debug] Could not parse SVG: {e}"

    total_notes = 0
    with_pitch = 0
    data_pitch = 0
    sample = []
    for el in _iter_svg_note_like(root):
        total_notes += 1
        has_direct = any(a in el.attrib for a in ('pname','accid','oct','midi'))
        has_data   = any(a in el.attrib for a in ('data-pname','data-accid','data-oct','data-midi'))
        if has_direct or has_data:
            with_pitch += 1
            if has_data: data_pitch += 1
            if len(sample) < 6:
                sample.append(_attrs(el))
    msg = f"[debug] notes={total_notes}, with_pitch={with_pitch}, with_data_attrs={data_pitch}"
    if sample:
        msg += "\n[debug] Sample note attribute dicts:\n" + "\n".join(f"   {i+1}: {s}" for i, s in enumerate(sample))
    else:
        msg += "\n[debug] No note carried pitch attributes on this page."
    return msg
