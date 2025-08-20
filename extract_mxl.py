import zipfile
from pathlib import Path

# Path to your MXL file
mxl_path = Path("Prelude_No._15_in_D_flat_major_Op._28_The_Raindrop_Prelude.mxl")

# Output folder where XML will be extracted
output_folder = Path("mxl_extracted")
output_folder.mkdir(exist_ok=True)

# Extract
with zipfile.ZipFile(mxl_path, 'r') as zf:
    zf.extractall(output_folder)

print("Extracted files:")
for f in output_folder.iterdir():
    print(f.name)
