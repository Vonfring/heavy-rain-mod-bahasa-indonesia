"""Bangun file patch distribusi (release/hr_id_patch.bin) dari build/ untuk patcher pemain.

Isi patch hanya rentang byte yang berubah pada data terdekompresi (bukan file game utuh), plus sha1
untuk verifikasi. Penempatan entri disimulasikan dengan plan_layout() milik patcher (identik dengan
repack.py) dari indeks ASLI (build/<Arsip>.idx.orig / .idm.orig), sehingga sha1 .idx/.idm hasil
patch juga tercatat dan bisa diverifikasi di komputer pemain.

Pemakaian: python tools/make_patch.py [--version 1.0]
Format: lihat docstring release/heavy-rain-indonesia/patcher/hr_patcher.py
"""
import os, sys, json, lzma, struct, hashlib, argparse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "release", "heavy-rain-indonesia", "patcher"))
import segs, hr_patcher
from bigfile import Index, Idm
sys.path.insert(1, os.path.join(ROOT, "tools"))
from repack import log_names, ARCHIVES as REPACK_ARCHIVES

BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(ROOT, "release", "hr_id_patch.bin")
BLOCK = 4096
GAP = 8                # rentang yang terpisah < GAP byte sama digabung

def sha1(b): return hashlib.sha1(b).hexdigest()

def diff_ranges(a, b):
    assert len(a) == len(b)
    rng = []
    for s in range(0, len(a), BLOCK):
        if a[s:s + BLOCK] == b[s:s + BLOCK]: continue
        e = min(s + BLOCK, len(a)); i = s
        while i < e:
            if a[i] != b[i]:
                j = i
                while j < e and a[j] != b[j]: j += 1
                if rng and i - (rng[-1][0] + rng[-1][1]) < GAP: rng[-1][1] = j - rng[-1][0]
                else: rng.append([i, j - i])
                i = j
            else: i += 1
    return rng

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--version", default="1.0"); a = ap.parse_args()
    manifest = json.load(open(os.path.join(BUILD, "manifest.json")))
    items, blob = [], bytearray()
    header = {"version": a.version, "archives": {}, "items": items}
    for arch, (_, log) in REPACK_ARCHIVES.items():
        idx_orig = os.path.join(BUILD, f"{arch}.idx.orig"); idm_orig = os.path.join(BUILD, f"{arch}.idm.orig")
        pkg_sizes = json.load(open(idx_orig + ".json"))["pkg_sizes"]
        ix = Index(idx_orig); used = ix.used_entries(); names = log_names(log)
        assert len(used) == len(names), "log unpack tidak cocok dengan indeks"
        by_name = {}
        for e, n in zip(used, names): by_name.setdefault(n, []).append(e)
        n_arch = 0
        for m in (m for m in manifest if m["archive"] == arch):
            ents = by_name.get(m["logname"])
            assert ents, m["logname"]
            orig = open(os.path.join(ROOT, m["orig"]), "rb").read()
            new = open(os.path.join(ROOT, m["build"]), "rb").read()
            is_s = segs.is_segs(orig)
            A = segs.decompress(orig) if is_s else orig
            B = segs.decompress(new) if is_s else new
            rng = diff_ranges(A, B)
            it = {"arch": arch, "name": m["logname"], "ents": [[e.i, e.type, e.fid] for e in ents],
                  "osha": sha1(orig), "osize": len(orig), "segs": is_s, "rng": rng, "blob": len(blob),
                  "rsha": sha1(B), "csha": sha1(new), "csize": len(new)}
            for off, ln in rng: blob += B[off:off + ln]
            assert hr_patcher.build_new(orig, it, blob) == new, f"rekonstruksi gagal: {m['logname']}"
            items.append(it); n_arch += 1
            print(f"\r{arch}: {n_arch} file, blob {len(blob) >> 10} KB", end="", flush=True)
        print()
        writes, idm_updates = hr_patcher.plan_layout(ix, pkg_sizes, [it for it in items if it["arch"] == arch])
        idm = Idm(idm_orig)
        for u in idm_updates: idm.update(*u)
        header["archives"][arch] = {
            "pkg_sizes": pkg_sizes,
            "idx_sha1": hr_patcher.file_sha1(idx_orig), "idm_sha1": hr_patcher.file_sha1(idm_orig),
            "idx_new_sha1": sha1(hr_patcher.idx_bytes(ix)), "idm_new_sha1": sha1(bytes(idm.data)),
            "inplace": sum(1 for w in writes if w[4]), "append": sum(1 for w in writes if not w[4])}
        print(f"  {arch}: {header['archives'][arch]['inplace']} di tempat, {header['archives'][arch]['append']} ditambahkan")
    hj = json.dumps(header, separators=(",", ":")).encode("utf-8")
    raw = hr_patcher.MAGIC + struct.pack(">I", len(hj)) + hj + bytes(blob)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "wb").write(lzma.compress(raw, preset=9 | lzma.PRESET_EXTREME))
    print(f"patch: {len(items)} file, mentah {len(raw) >> 10} KB -> {OUT} ({os.path.getsize(OUT) >> 10} KB)")

if __name__ == "__main__":
    main()
