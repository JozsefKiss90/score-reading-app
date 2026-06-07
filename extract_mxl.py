import zipfile
from pathlib import Path

# Path to your MXL file
mxl_path = Path("resources\\organ-sonata-no-4-bwv-528-2-andante-adagio-vikingur-olafsson-interpretation.mxl")

# Output folder where XML will be extracted
output_folder = Path("mxl_extracted")
output_folder.mkdir(exist_ok=True)

# Extract
with zipfile.ZipFile(mxl_path, 'r') as zf:
    zf.extractall(output_folder)

print("Extracted files:")
for f in output_folder.iterdir():
    print(f.name)
