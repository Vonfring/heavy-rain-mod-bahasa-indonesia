"""Pembaca/penulis indeks arsip BigFile Quantic Dream (versi 13, Heavy Rain PC).

Layout .idx (big-endian):
  0x00  'QUANTICDREAMTABINDEX' (20 byte)
  0x14  u32 versi (13)
  0x18  u32 tidak diketahui (0xffff)
  0x1C  72 byte 'ZEP...' sub-magic
  0x64  u32 jumlah entri
  lalu per entri 7 x u32: tipe, flag, fileID, offset, size, paddedSize, packageID
  packageID 0 -> <base>.dat, N -> <base>.dNN
Slot data disusun rata 0x800 byte.
"""
import struct, os

HDR = 0x68
ENT = 28
ALIGN = 0x800

class Entry:
    __slots__ = ("i", "type", "flag", "fid", "offset", "size", "padded", "pkg")
    def __init__(self, i, vals):
        self.i = i; (self.type, self.flag, self.fid, self.offset, self.size, self.padded, self.pkg) = vals
    def vals(self): return (self.type, self.flag, self.fid, self.offset, self.size, self.padded, self.pkg)
    @property
    def used(self): return self.size != 0 or self.padded != 0

class Index:
    def __init__(self, idx_path):
        self.path = idx_path
        self.base = os.path.splitext(idx_path)[0]
        d = open(idx_path, "rb").read()
        assert d[:20] == b"QUANTICDREAMTABINDEX", "magic idx salah"
        self.version = struct.unpack(">I", d[20:24])[0]
        assert self.version == 13, f"versi idx {self.version} tidak didukung"
        self.header = d[:HDR]
        n = struct.unpack(">I", d[HDR-4:HDR])[0]
        self.entries = [Entry(i, struct.unpack(">7I", d[HDR+i*ENT:HDR+(i+1)*ENT])) for i in range(n)]
        self.tail = d[HDR+n*ENT:]

    def package_path(self, pkg):
        return self.base + (".dat" if pkg == 0 else f".d{pkg:02d}")

    def used_entries(self):
        return [e for e in self.entries if e.used]

    def slot_capacity(self):
        """Kapasitas slot tiap entri = jarak ke entri berikutnya di paket yang sama (atau ke akhir file)."""
        cap = {}
        by_pkg = {}
        for e in self.used_entries(): by_pkg.setdefault(e.pkg, []).append(e)
        for pkg, es in by_pkg.items():
            es.sort(key=lambda e: e.offset)
            end = os.path.getsize(self.package_path(pkg))
            for a, b in zip(es, es[1:] + [None]):
                nxt = b.offset if b else end
                cap[a.i] = nxt - a.offset
        return cap

    def write(self, out_path=None):
        out = bytearray(self.header)
        for e in self.entries: out += struct.pack(">7I", *e.vals())
        out += self.tail
        open(out_path or self.path, "wb").write(out)

def align(n, a=ALIGN): return (n + a - 1) // a * a


class Idm:
    """Salinan indeks yang dibaca game saat runtime (<base>.idm, magic QUANTICDREAMTABIDMEM).

    Layout (big-endian):
      0x00  magic 20 byte
      0x14  header 12 byte (0000ffff, versi, 0)
      0x20  tabel tipe: (typeID, jumlah, offset) sampai data; offset relatif ke 0x14
      blok per tipe: tabel hash 1024 byte (256 x u32) lalu jumlah x 20 byte:
            fileID, offset, size, paddedSize, packageID<<24
    """
    def __init__(self, path):
        self.path = path
        self.data = bytearray(open(path, "rb").read())
        assert self.data[:20] == b"QUANTICDREAMTABIDMEM", "magic idm salah"
        u = lambda o: struct.unpack(">I", self.data[o:o+4])[0]
        q = 32; self.types = []
        while True:
            t, c, o = u(q), u(q+4), u(q+8)
            if not (0 < t < 0x20000 and 0 < c < 100000): break
            self.types.append((t, c, o)); q += 12
        self.pos = {}                      # (type, fid, offset, size) -> posisi entri 20 byte
        for t, c, o in self.types:
            st = 0x14 + o + 1024
            for k in range(c):
                fid, off, size = struct.unpack(">III", self.data[st+k*20:st+k*20+12])
                self.pos[(t, fid, off, size)] = st + k*20

    def update(self, type_, fid, old_off, old_size, new_off, new_size, new_pkg):
        p = self.pos.pop((type_, fid, old_off, old_size))
        padded = struct.unpack(">I", self.data[p+12:p+16])[0]
        self.data[p:p+20] = struct.pack(">IIIII", fid, new_off, new_size, padded, new_pkg << 24)
        self.pos[(type_, fid, new_off, new_size)] = p

    def write(self, out_path=None):
        open(out_path or self.path, "wb").write(self.data)
