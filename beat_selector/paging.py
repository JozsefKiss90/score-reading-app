
from __future__ import annotations
from typing import Dict, List, Tuple
import xml.etree.ElementTree as ET
import verovio
from .data import Measure

def discover_pages_by_numbers(tk: verovio.toolkit, measures: List[Measure]) -> Tuple[List[str], List[List[int]]]:
    page_count = int(tk.getPageCount() or 1)
    page_svgs: List[str] = []
    page_abs_indexes: List[List[int]] = []

    num_to_abs: Dict[int, int] = {}
    for m in measures:
        if m.number not in num_to_abs:
            num_to_abs[m.number] = m.index

    for p in range(page_count):
        svg = tk.renderToSVG(p+1)
        page_svgs.append(svg)
        abs_list: List[int] = []
        try:
            root = ET.fromstring(svg)
            for g in root.iter():
                tag = g.tag.split('}')[-1]
                if tag != 'g': continue
                typ = g.attrib.get('data-vrv-type') or g.attrib.get('data-type') or ''
                if typ != 'measure' and 'measure' not in g.attrib.get('class',''): continue
                n_attr = g.attrib.get('n') or g.attrib.get('data-n') or ''
                num = None
                try:
                    if n_attr: num = int(str(n_attr).strip().split()[0])
                except: num = None
                if num is not None and num in num_to_abs:
                    abs_idx = num_to_abs[num]
                else:
                    abs_idx = (abs_list[-1]+1) if abs_list else sum(len(x) for x in page_abs_indexes)
                    abs_idx = min(abs_idx, len(measures)-1)
                abs_list.append(abs_idx)
        except Exception:
            count = svg.count('data-vrv-type="measure"') or svg.count('class="measure"') or 1
            base = sum(len(x) for x in page_abs_indexes)
            abs_list = [min(base+i, len(measures)-1) for i in range(count)]
        page_abs_indexes.append(abs_list)

    if not page_abs_indexes:
        page_abs_indexes = [[i for i in range(len(measures))]]
    return page_svgs, page_abs_indexes
