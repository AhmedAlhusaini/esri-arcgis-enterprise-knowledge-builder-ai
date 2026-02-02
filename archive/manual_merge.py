import os
from pypdf import PdfWriter

SOURCE_DIR = "ArcGIS Enterprise"
OUTPUT_FILE = "ArcGIS_Enterprise_Complete.pdf"

def main():
    if not os.path.exists(SOURCE_DIR):
        print(f"Directory {SOURCE_DIR} not found.")
        return

    files = sorted([f for f in os.listdir(SOURCE_DIR) if f.endswith('.pdf')])
    if not files:
        print("No PDFs found.")
        return

    print(f"Merging {len(files)} PDFs from '{SOURCE_DIR}'...")
    merger = PdfWriter()
    
    count = 0
    for fname in files:
        try:
            merger.append(os.path.join(SOURCE_DIR, fname))
            count += 1
        except Exception as e:
            print(f"Skipping {fname}: {e}")

    with open(OUTPUT_FILE, "wb") as f_out:
        merger.write(f_out)
    
    print(f"Success! Merged {count} pages into {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
