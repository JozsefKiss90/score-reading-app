import xml.etree.ElementTree as ET
from collections import defaultdict

def extract_notes_by_staff(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    for part in root.findall(".//part"):
        for measure in part.findall("measure"):
            measure_num = measure.attrib.get("number", "?")
            notes_by_staff = defaultdict(list)

            for note in measure.findall("note"):
                staff = note.findtext("staff", default="1")  # default to staff 1 if not specified

                if note.find("rest") is not None:
                    rest_type = note.findtext("type", "unknown")
                    duration = note.findtext("duration", "unknown")
                    notes_by_staff[staff].append(f"Rest (duration {duration})")
                else:
                    pitch = note.find("pitch")
                    if pitch is not None:
                        step = pitch.findtext("step", "?")
                        alter = pitch.findtext("alter")
                        octave = pitch.findtext("octave", "?")
                        accidental = "#" if alter == "1" else "b" if alter == "-1" else ""
                        duration = note.findtext("duration", "?")
                        notes_by_staff[staff].append(f"Note: {step}{accidental}{octave} (duration {duration})")

            print(f"Measure {measure_num}:")
            for staff_num, notes in sorted(notes_by_staff.items()):
                print(f"  Staff {staff_num}:")
                for note_desc in notes:
                    print(f"    - {note_desc}")
            print()

def main():
    xml_path = "Gymnopdie\score.xml"
    extract_notes_by_staff(xml_path)

if __name__ == "__main__":
    main()
