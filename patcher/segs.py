"""Dekompresi/kompresi container 'segs' (Quantic Dream, Heavy Rain PC).

Layout (semua big-endian):
  0x00  'segs'
  0x04  u16 version (1)
  0x06  u16 jumlah segmen
  0x08  u32 ukuran hasil dekompresi
  0x0C  u32 ukuran area data terkompresi
  0x10  tabel entri, 8 byte per segmen: u16 csize (0 = 65536), u16 usize (0 = 65536), u32 offset
        offset relatif ke awal area data; bit terendah = flag 'terkompresi'
  data  mulai di offset tabel-akhir yang dibulatkan ke kelipatan 16; tiap segmen rata 16 byte
Tiap segmen terkompresi = raw deflate (zlib wbits=-15).
"""
import struct, zlib, sys, os

SEG = 0x10000
NUL = bytes(1)


def is_segs(data: bytes) -> bool:
    return data[:4] == b"segs"


def decompress(data: bytes) -> bytes:
    if not is_segs(data):
        raise ValueError("bukan file segs")
    ver, count = struct.unpack(">HH", data[4:8])
    usize_total, csize_total = struct.unpack(">II", data[8:16])
    ents = [struct.unpack(">HHI", data[16 + i*8:24 + i*8]) for i in range(count)]
    data_start = (16 + count*8 + 15) & ~15
    out = bytearray()
    for cs, us, off in ents:
        us = us or SEG
        cs = cs or SEG
        compressed = off & 1
        start = data_start + (off & ~1)
        chunk = data[start:start + cs]
        seg = zlib.decompress(chunk, -15) if compressed else chunk[:us]
        if len(seg) != us:
            raise ValueError(f"segmen salah ukuran: dapat {len(seg)} harap {us}")
        out += seg
    if len(out) != usize_total:
        raise ValueError(f"total salah ukuran: dapat {len(out)} harap {usize_total}")
    return bytes(out)


CHUNK = 0x100000   # game membaca file per 1 MB: satu segmen tidak boleh melintasi batas ini (offset absolut)


def compress(raw: bytes, level: int = 9) -> bytes:
    """Bangun container segs dari data mentah, meniru layout asli byte demi byte:
    - segmen 64 KB, raw deflate level 9 (memLevel 8), segmen disimpan mentah bila tidak mengecil
    - tiap segmen rata 16 byte (celah diisi nol)
    - segmen yang akan melintasi batas 1 MB (offset absolut file) dipindah ke batas berikutnya;
      celahnya diisi salinan awal segmen itu (persis seperti penulis asli)"""
    parts = [raw[i:i + SEG] for i in range(0, len(raw), SEG)] or [b""]
    count = len(parts)
    data_start = (16 + count*8 + 15) & ~15
    table = bytearray()
    body = bytearray()
    for k, seg in enumerate(parts):
        c = zlib.compressobj(level, zlib.DEFLATED, -15)
        comp = c.compress(seg) + c.flush()
        if len(comp) < len(seg) and len(comp) < SEG:
            chunk, flag = comp, 1
        else:
            chunk, flag = seg, 0
        pos = len(body)
        absolute = data_start + pos
        if absolute // CHUNK != (absolute + len(chunk) - 1) // CHUNK:
            boundary = (absolute // CHUNK + 1) * CHUNK
            body += chunk[:boundary - absolute]
            pos = len(body)
        us = 0 if len(seg) == SEG else len(seg)
        cs = 0 if len(chunk) == SEG else len(chunk)
        table += struct.pack(">HHI", cs, us, pos | flag)
        body += chunk
        if k != count - 1:
            body += NUL * ((-len(body)) & 15)
    head = b"segs" + struct.pack(">HHII", 1, count, len(raw), len(body))
    out = head + bytes(table)
    out += NUL * (data_start - len(out))
    return bytes(out + body)


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    d = open(src, "rb").read()
    open(dst, "wb").write(decompress(d) if is_segs(d) else compress(d))
    print("ok", os.path.getsize(dst))
