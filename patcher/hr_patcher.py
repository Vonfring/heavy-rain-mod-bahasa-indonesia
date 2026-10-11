"""Patcher Mod Bahasa Indonesia untuk Heavy Rain (Steam, PC).

Membaca file asli dari arsip game milik pemain, menerapkan patch selisih byte (hr_id_patch.bin),
mengompresi ulang (segs), lalu menulis kembali ke arsip dan memperbarui indeks .idx dan .idm.
Bahasa Indonesia ditaruh di slot bahasa Danish (pilih "INDO" untuk Subtitle dan Menu).

Format hr_id_patch.bin (dikompresi lzma):
  'HRIDPATCH1' | u32 panjang header | header JSON | blob rentang byte
Header: versi, per arsip (sha1 idx/idm asli & hasil, ukuran paket), daftar item
  item: arsip, entri [[indeks, tipe, fid]], sha1 & ukuran asli, segs?, rentang [[offset, panjang]],
        posisi blob, sha1 hasil dekompresi, sha1 & ukuran hasil kompresi

Pemakaian: HeavyRain-Indonesia-Patcher.exe  (atau: python hr_patcher.py [--game <folder>] [--patch <file>])
"""
import os, sys, json, lzma, struct, hashlib, shutil, subprocess, argparse, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import segs
from bigfile import Index, Idm, align

MAGIC = b"HRIDPATCH1"
MARKER = "HR_ID_PATCH.json"
BACKUP_DIR = "HR_ID_BACKUP"
ARCHIVES = {"BigFile": os.path.join("Resources", "BigFile_WIN.idx"),
            "GameData": os.path.join("Resources", "GameData", "GameData_WIN.idx")}

def sha1(b): return hashlib.sha1(b).hexdigest()
def file_sha1(p):
    h = hashlib.sha1()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()

# ---------- format patch ----------
def load_patch(path):
    d = lzma.decompress(open(path, "rb").read())
    assert d[:len(MAGIC)] == MAGIC, "file patch tidak valid"
    n = struct.unpack(">I", d[len(MAGIC):len(MAGIC) + 4])[0]
    p = len(MAGIC) + 4
    header = json.loads(d[p:p + n].decode("utf-8"))
    return header, memoryview(d)[p + n:]

def apply_ranges(raw, item, blob):
    out = bytearray(raw)
    pos = item["blob"]
    for off, ln in item["rng"]:
        out[off:off + ln] = blob[pos:pos + ln]; pos += ln
    return bytes(out)

def build_new(orig, item, blob):
    """Bytes asli satu file -> bytes hasil patch (terkompresi bila aslinya segs). Diverifikasi sha1."""
    raw = segs.decompress(orig) if item["segs"] else orig
    new_raw = apply_ranges(raw, item, blob)
    if sha1(new_raw) != item["rsha"]: raise ValueError("hasil patch tidak cocok (rsha)")
    return segs.compress(new_raw) if item["segs"] else new_raw

# ---------- penempatan (identik dengan tools/repack.py) ----------
def slot_capacity(ix, pkg_sizes):
    cap, by_pkg = {}, {}
    for e in ix.used_entries(): by_pkg.setdefault(e.pkg, []).append(e)
    for pkg, es in by_pkg.items():
        es.sort(key=lambda e: e.offset)
        end = pkg_sizes[str(pkg)]
        for a, b in zip(es, es[1:] + [None]):
            cap[a.i] = (b.offset if b else end) - a.offset
    return cap

def plan_layout(ix, pkg_sizes, items):
    """Tentukan posisi tulis tiap entri. Mengubah entri di ix (offset/size/pkg).
    Kembalikan daftar (item, entri, pkg, offset_tulis, inplace, nilai_lama) dan pembaruan idm."""
    cap = slot_capacity(ix, pkg_sizes)
    last_pkg = max(e.pkg for e in ix.used_entries())
    append_pos = pkg_sizes[str(last_pkg)]
    writes, idm_updates = [], []
    for it in items:
        for i, typ, fid in it["ents"]:
            e = ix.entries[i]
            assert (e.type, e.fid) == (typ, fid), "indeks arsip tidak cocok"
            old = (e.pkg, e.offset, e.size)
            if it["csize"] <= cap[e.i]:
                writes.append((it, e.i, e.pkg, e.offset, True, old))
                idm_updates.append((e.type, e.fid, e.offset, e.size, e.offset, it["csize"], e.pkg))
                e.size = it["csize"]
            else:
                pos = align(append_pos)
                writes.append((it, e.i, last_pkg, pos, False, old))
                idm_updates.append((e.type, e.fid, e.offset, e.size, pos, it["csize"], last_pkg))
                e.pkg, e.offset, e.size = last_pkg, pos, it["csize"]
                append_pos = pos + it["csize"]
    return writes, idm_updates

def idx_bytes(ix):
    out = bytearray(ix.header)
    for e in ix.entries: out += struct.pack(">7I", *e.vals())
    return bytes(out + ix.tail)

# ---------- folder game ----------
def steam_libraries():
    roots = []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for name in ("SteamPath", "InstallPath"):
                        try: roots.append(winreg.QueryValueEx(k, name)[0])
                        except OSError: pass
            except OSError: pass
    except ImportError: pass
    libs = []
    for r in roots:
        libs.append(r)
        vdf = os.path.join(r, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf):
            for line in open(vdf, encoding="utf-8", errors="ignore"):
                parts = line.strip().split('"')
                if len(parts) >= 4 and parts[1] == "path": libs.append(parts[3].replace("\\\\", "\\"))
    return libs

def is_game_dir(d):
    return d and all(os.path.exists(os.path.join(d, p)) for p in ARCHIVES.values())

def find_game():
    here = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    cands = [here, os.path.dirname(here), os.getcwd()]
    cands += [os.path.join(l, "steamapps", "common", "Heavy Rain") for l in steam_libraries()]
    for c in cands:
        if is_game_dir(c): return os.path.normpath(c)
    return None

def game_running():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq HeavyRain.exe"], capture_output=True, text=True).stdout
        return "HeavyRain.exe" in out
    except OSError:
        return False

# ---------- status ----------
def status(game, header):
    """'asli' / 'terpasang' / 'lain' per arsip -> ringkasan."""
    st = {}
    for arch, rel in ARCHIVES.items():
        idx = os.path.join(game, rel); h = file_sha1(idx); a = header["archives"][arch]
        st[arch] = "asli" if h == a["idx_sha1"] else "terpasang" if h == a["idx_new_sha1"] else "lain"
    vals = set(st.values())
    return vals.pop() if len(vals) == 1 else "campuran"

# ---------- pasang ----------
def install(game, header, blob, backup):
    res = os.path.join(game, "Resources")
    bdir = os.path.join(res, BACKUP_DIR)
    plans = {}
    print("\n[1/3] Memeriksa file game ...")
    for arch, rel in ARCHIVES.items():
        a = header["archives"][arch]; idx_path = os.path.join(game, rel)
        ix = Index(idx_path)
        for pkg, size in a["pkg_sizes"].items():
            if os.path.getsize(ix.package_path(int(pkg))) != size:
                raise SystemExit(f"Ukuran {os.path.basename(ix.package_path(int(pkg)))} berbeda dari versi yang didukung.\n"
                                 "Jalankan 'Verify integrity of game files' di Steam lalu coba lagi.")
        items = [it for it in header["items"] if it["arch"] == arch]
        writes, idm_updates = plan_layout(ix, a["pkg_sizes"], items)
        plans[arch] = (idx_path, ix, writes, idm_updates)
        orig_ix = Index(idx_path)
        for k, (it, ei, *_rest) in enumerate(writes):
            e = orig_ix.entries[ei]
            with open(ix.package_path(e.pkg), "rb") as fh: fh.seek(e.offset); cur = fh.read(e.size)
            if e.size != it["osize"] or sha1(cur) != it["osha"]:
                raise SystemExit(f"File game {it['name']} tidak cocok dengan versi yang didukung.\n"
                                 "Jalankan 'Verify integrity of game files' di Steam lalu coba lagi.")
            print(f"\r  {arch}: {k + 1}/{len(writes)}", end="", flush=True)
        print()
    if backup:
        need = sum(w[5][2] for p in plans.values() for w in p[2] if w[4])
        free = shutil.disk_usage(res).free
        if free < need + (500 << 20):
            raise SystemExit(f"Ruang disk kurang untuk backup ({need >> 20} MB dibutuhkan, {free >> 20} MB tersedia).")
        os.makedirs(bdir, exist_ok=True)
    print("[2/3] Memasang patch (beberapa menit) ...")
    t0 = time.time()
    for arch, (idx_path, ix, writes, idm_updates) in plans.items():
        a = header["archives"][arch]
        if backup:
            shutil.copyfile(idx_path, os.path.join(bdir, arch + ".idx"))
            shutil.copyfile(idx_path[:-4] + ".idm", os.path.join(bdir, arch + ".idm"))
            json.dump({"pkg_sizes": a["pkg_sizes"]}, open(os.path.join(bdir, arch + ".json"), "w"))
            journal = open(os.path.join(bdir, arch + ".journal"), "wb")
        cache = {}
        for k, (it, ei, pkg, off, inplace, old) in enumerate(writes):
            opkg, ooff, osize = old
            with open(ix.package_path(opkg), "rb") as fh: fh.seek(ooff); orig = fh.read(osize)
            new = build_new(orig, it, blob)
            if len(new) != it["csize"] or sha1(new) != it["csha"]: raise SystemExit(f"Gagal membangun {it['name']}")
            if inplace and backup: journal.write(struct.pack(">III", opkg, ooff, osize) + orig)
            if pkg not in cache: cache[pkg] = open(ix.package_path(pkg), "r+b")
            cache[pkg].seek(off); cache[pkg].write(new)
            print(f"\r  {arch}: {k + 1}/{len(writes)}", end="", flush=True)
        for f in cache.values(): f.close()
        if backup: journal.close()
        open(idx_path, "wb").write(idx_bytes(ix))
        idm = Idm(idx_path[:-4] + ".idm")
        for u in idm_updates: idm.update(*u)
        idm.write()
        print()
    print(f"[3/3] Verifikasi ... ({time.time() - t0:.0f} detik)")
    ok = True
    for arch, (idx_path, ix, writes, _) in plans.items():
        a = header["archives"][arch]
        if file_sha1(idx_path) != a["idx_new_sha1"] or file_sha1(idx_path[:-4] + ".idm") != a["idm_new_sha1"]: ok = False
        for it, ei, pkg, off, *_ in writes:
            with open(ix.package_path(pkg), "rb") as fh: fh.seek(off); cur = fh.read(it["csize"])
            if sha1(cur) != it["csha"]: ok = False
    json.dump({"versi": header["version"], "tanggal": time.strftime("%Y-%m-%d %H:%M"), "backup": backup},
              open(os.path.join(res, MARKER), "w"), indent=1)
    if not ok: raise SystemExit("Verifikasi GAGAL. Copot patch atau jalankan 'Verify integrity of game files' di Steam.")
    print("\nSelesai! Buka game -> menu Language/Bahasa, lalu pilih DANISH untuk Subtitle dan Menu.\n"
          "Setelah menu berganti ke bahasa Indonesia, pilihan itu akan tertulis INDO.")

# ---------- copot ----------
def uninstall(game):
    res = os.path.join(game, "Resources"); bdir = os.path.join(res, BACKUP_DIR)
    if not os.path.isdir(bdir) or not all(os.path.exists(os.path.join(bdir, a + ".idx")) for a in ARCHIVES):
        print("\nTidak ada backup. Untuk mengembalikan game ke bahasa asli:\n"
              "  Steam -> klik kanan Heavy Rain -> Properties -> Installed Files -> Verify integrity of game files")
        return
    for arch, rel in ARCHIVES.items():
        idx_path = os.path.join(game, rel); ix = Index(os.path.join(bdir, arch + ".idx"))
        ix.base = os.path.splitext(idx_path)[0]
        jp = os.path.join(bdir, arch + ".journal")
        with open(jp, "rb") as fh:
            while True:
                head = fh.read(12)
                if len(head) < 12: break
                pkg, off, n = struct.unpack(">III", head); data = fh.read(n)
                with open(ix.package_path(pkg), "r+b") as pf: pf.seek(off); pf.write(data)
        meta = json.load(open(os.path.join(bdir, arch + ".json")))
        for pkg, size in meta["pkg_sizes"].items():
            p = ix.package_path(int(pkg))
            if os.path.getsize(p) > size:
                with open(p, "r+b") as pf: pf.truncate(size)
        shutil.copyfile(os.path.join(bdir, arch + ".idx"), idx_path)
        shutil.copyfile(os.path.join(bdir, arch + ".idm"), idx_path[:-4] + ".idm")
        print(f"  {arch}: dipulihkan")
    shutil.rmtree(bdir)
    if os.path.exists(os.path.join(res, MARKER)): os.remove(os.path.join(res, MARKER))
    print("\nPatch dicopot, game kembali seperti semula.")

# ---------- antarmuka ----------
def ask(prompt, default="y"):
    a = input(prompt).strip().lower()
    return (a or default).startswith("y")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game"); ap.add_argument("--patch")
    a = ap.parse_args()
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    patch_path = a.patch or os.path.join(base, "hr_id_patch.bin")
    header, blob = load_patch(patch_path)
    print(f"=== Heavy Rain - Mod Bahasa Indonesia v{header['version']} ===\n")
    game = a.game or find_game()
    while not is_game_dir(game):
        game = input("Folder Heavy Rain tidak ditemukan. Tempel path foldernya\n"
                     "(contoh: C:\\Program Files (x86)\\Steam\\steamapps\\common\\Heavy Rain): ").strip().strip('"')
    print("Folder game:", game)
    st = status(game, header)
    print("Status     :", {"asli": "belum terpasang", "terpasang": "SUDAH terpasang",
                           "lain": "file game berbeda / versi lain", "campuran": "sebagian terpasang"}[st])
    print("\n[1] Pasang bahasa Indonesia\n[2] Copot (kembalikan ke asli)\n[3] Keluar")
    pick = input("Pilih: ").strip()
    if pick not in ("1", "2"): return
    if game_running(): raise SystemExit("Tutup Heavy Rain dulu, lalu jalankan patcher lagi.")
    if pick == "1":
        if st == "terpasang": print("Patch sudah terpasang."); return
        if st != "asli":
            raise SystemExit("File game tidak dalam kondisi asli. Jalankan 'Verify integrity of game files' di Steam "
                             "(atau copot patch lama), lalu coba lagi.")
        backup = ask("Simpan backup agar bisa dicopot tanpa internet? Butuh +-1,5 GB ruang disk [Y/n]: ")
        install(game, header, blob, backup)
    else:
        uninstall(game)

if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        if e.code not in (None, 0): print("\n" + str(e.code))
    except Exception as e:
        print("\nTerjadi kesalahan:", repr(e))
    if getattr(sys, "frozen", False): input("\nTekan Enter untuk keluar...")
