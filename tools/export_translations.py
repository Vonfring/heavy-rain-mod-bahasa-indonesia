"""Ekspor terjemahan untuk repo publik: hanya kunci + teks Indonesia (tanpa teks asli ENG/DAN milik game).

Input : text/translate_subtitle.csv, translate_labels.csv, translate_scene_names.csv, translate_menu.csv
Output: release/heavy-rain-indonesia/translations/*.csv
"""
import os, csv
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "text")
DST = os.path.join(ROOT, "release", "heavy-rain-indonesia", "translations")

FILES = {   # sumber -> (output, kolom yang diekspor)
    "translate_subtitle.csv":    ("subtitle.csv",    ["key", "IND", "catatan"]),
    "translate_labels.csv":      ("labels.csv",      ["key", "IND"]),
    "translate_scene_names.csv": ("scene_names.csv", ["name", "IND"]),
    "translate_menu.csv":        ("menu.csv",        ["key", "batas_karakter", "IND"]),
}

def main():
    os.makedirs(DST, exist_ok=True)
    for src, (out, cols) in FILES.items():
        rows = list(csv.DictReader(open(os.path.join(SRC, src), encoding="utf-8-sig")))
        rows = [r for r in rows if r["IND"].strip()]
        with open(os.path.join(DST, out), "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(cols)
            for r in rows: w.writerow([r[c] for c in cols])
        print(f"{out}: {len(rows)} baris")

if __name__ == "__main__":
    main()
