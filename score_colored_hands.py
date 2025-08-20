#!/usr/bin/env python3

import os
from lxml import etree

INPUT_FILE = "Gymnopdie_No.mei"
OUTPUT_FILE = "Gymnopdie_No_colored.mei"

def remove_namespace(tree):
    for elem in tree.iter():
        if not hasattr(elem.tag, 'find'):
            continue
        i = elem.tag.find("}")
        if i != -1:
            elem.tag = elem.tag[i + 1:]
    return tree

def color_mei_by_staff(input_path, output_path):
    if not os.path.exists(input_path):
        print(f"❌ Input file not found: {input_path}")
        return

    print(f"🔍 Reading {input_path} ...")
    tree = etree.parse(input_path)
    tree = remove_namespace(tree)
    root = tree.getroot()

    staff_count = 0
    note_count = 0

    for staff in root.findall(".//staff"):
        staff_n = staff.get("n")
        staff_count += 1
        for layer in staff.findall(".//layer"):
            for note in layer.findall(".//note"):
                if staff_n == "1":
                    note.set("color", "#007ACC")  # Right hand: blue
                elif staff_n == "2":
                    note.set("color", "#FF4C4C")  # Left hand: red
                note_count += 1

    print(f"🎯 Colored {note_count} notes in {staff_count} staves.")
    tree.write(output_path, pretty_print=True, xml_declaration=True, encoding="UTF-8")
    print(f"✅ Output written: {os.path.abspath(output_path)}")

if __name__ == "__main__":
    color_mei_by_staff(INPUT_FILE, OUTPUT_FILE)
