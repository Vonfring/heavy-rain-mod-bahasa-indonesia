# Heavy Rain: Mod Bahasa Indonesia

Mod buatan penggemar yang menerjemahkan **Heavy Rain (PC, Steam)** ke bahasa Indonesia:

- Subtitle seluruh dialog (3.446 baris)
- Label pilihan/aksi di layar (836)
- Judul bab (101)
- Menu dan antarmuka (1.148)

Audio tetap memakai dubbing asli (Inggris atau bahasa lain yang tersedia).

> Bahasa Indonesia dipasang di **slot bahasa Danish**. Setelah dipasang, subtitle dan menu Danish berganti jadi bahasa Indonesia.

## Syarat

- Heavy Rain versi **Steam** yang sudah diperbarui ke versi terbaru. Versi Epic Games/GOG belum diuji.
- Windows 64-bit.
- Ruang disk kosong ±200 MB. Tambah ±1,5 GB kalau memilih menyimpan backup.

## Cara pasang

1. Tutup Heavy Rain.
2. Unduh `HeavyRain-Indonesia-Patcher-vX.Y.zip` dari halaman [Releases](../../releases), lalu ekstrak.
3. Jalankan `HeavyRain-Indonesia-Patcher.exe`. Folder game dicari otomatis. Kalau tidak ketemu, tempel path foldernya.
4. Pilih **[1] Pasang**. Kalau ditanya soal backup, pilih **Y** agar mod bisa dicopot tanpa internet.
5. Tunggu sampai muncul tulisan **Selesai!** (beberapa menit).

### Mengaktifkan di game

Buka menu **Language** di game, lalu ubah **Subtitle** dan **Menu** ke **DANISH**. Setelah menu berganti ke bahasa Indonesia, pilihan itu akan tertulis **INDO**.

## Cara copot

- **Kalau dulu memilih backup:** jalankan patcher, lalu pilih **[2] Copot**.
- **Kalau tidak memilih backup:** di Steam, klik kanan Heavy Rain → Properties → Installed Files → **Verify integrity of game files**. Steam akan mengunduh ulang file yang berubah.

Kalau game mendapat update dari Steam, patch mungkin tertimpa. Jalankan patcher lagi setelah update (atau tunggu versi patch baru kalau patcher menolak).

## Masalah yang diketahui

- Nama bahasa di menu hanya tertulis **INDO**, karena ruang teks slot Danish maksimal 7 huruf.
- Subtitle dan menu bahasa Danish asli tidak tersedia selama mod terpasang.
- Beberapa teks tutorial yang panjang sedikit terpotong karena keterbatasan ruang.
- Antivirus kadang menandai .exe buatan PyInstaller sebagai mencurigakan (false positive). Kode sumber patcher ada di folder [`patcher/`](patcher/). Cocokkan SHA-256 file dengan yang tertulis di halaman rilis.

## Cara kerja (singkat)

Patcher **tidak berisi file game**. Isinya hanya selisih teks (`hr_id_patch.bin`). Saat dijalankan, patcher:

1. Memeriksa sha1 file game, untuk memastikan versinya cocok dan belum diubah.
2. Membaca file asli dari arsip `BigFile_WIN` dan `GameData_WIN` di komputer kamu, menyisipkan teks Indonesia, lalu mengompresi ulang.
3. Menulis kembali ke arsip, memperbarui indeks `.idx`/`.idm`, lalu memverifikasi hasilnya.

Menjalankan dari kode sumber (perlu Python 3.10+):

```
python patcher/hr_patcher.py --patch hr_id_patch.bin
```

## Terjemahan

File terjemahan ada di [`translations/`](translations/) (kunci + teks Indonesia). Laporan salah ketik atau terjemahan yang kurang pas bisa dikirim lewat **Issues**. Sertakan screenshot dan nama babnya.

## Kredit

- Terjemahan dan patcher: Vonfring
- Riset format arsip BigFile: [Ekey / QD.BIG.Tool](https://github.com/Ekey/QD.BIG.Tool)

## Disclaimer

Ini mod **tidak resmi** buatan penggemar dan tidak berafiliasi dengan Quantic Dream maupun penerbitnya. Heavy Rain dan semua asetnya adalah milik Quantic Dream. Mod ini gratis, tidak boleh dijual, dan membutuhkan salinan game yang sah. Gunakan dengan risiko sendiri.

## Lisensi

- Kode (folder `patcher/`, `tools/`): [MIT](LICENSE)
- Terjemahan (folder `translations/`): [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.id)
