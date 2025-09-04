
================================
🤖 BOT MANGA DOWNLOADER README
================================

📚 TENTANG BOT INI
==================
Bot Telegram untuk download manga dari website Komiku.org dengan fitur:
- Download manga dalam format PDF
- Mode Normal dan Mode Komik (resolusi tinggi)
- Upload otomatis ke Google Drive untuk file besar
- Gabung multiple chapter atau pisah per chapter
- Auto demo untuk testing
- Smart monitoring dan error recovery

🚀 FITUR UTAMA
==============
1. Mode Download:
   - Mode Normal (/manga): Download standar
   - Mode Komik (/komik): Download dengan resolusi lebih tinggi (max 3 chapter)

2. Format Output:
   - Gabung: Semua chapter jadi 1 PDF
   - Pisah: 1 PDF per chapter

3. Upload Options:
   - Telegram Direct: Max 50MB
   - Google Drive: Unlimited size

4. Commands:
   - /start - Mulai bot
   - /manga - Mode download normal
   - /komik - Mode download komik
   - /cancel - Hentikan download
   - /clear - Hapus pesan bot
   - /autodemo - Demo otomatis
   - /offautodemo - Stop demo

⚙️ CARA INSTALL DEPENDENCIES
============================
1. Buka Terminal/Shell di Replit
2. Jalankan command:
   pip install -r requirements.txt

Atau dependencies akan ter-install otomatis saat run bot.

Dependencies yang dibutuhkan:
- requests: untuk HTTP requests
- beautifulsoup4: untuk parsing HTML
- Pillow: untuk manipulasi gambar
- pyTelegramBotAPI: untuk Telegram Bot API
- flask: untuk keep-alive server
- python-dotenv: untuk environment variables
- google-api-python-client: untuk Google Drive API
- google-auth-httplib2: untuk Google auth
- google-auth-oauthlib: untuk OAuth

🔑 CARA DAPATKAN TOKEN BOT TELEGRAM
===================================
1. Buka Telegram dan cari @BotFather
2. Kirim command /newbot
3. Masukkan nama bot (contoh: My Manga Bot)
4. Masukkan username bot (harus diakhiri 'bot', contoh: mymangadownloader_bot)
5. BotFather akan memberikan token seperti: 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
6. Copy token tersebut
7. Di Replit, buka tab "Secrets" (ikon gembok)
8. Buat secret baru:
   - Key: BOT_TOKEN
   - Value: paste token dari BotFather

☁️ CARA DAPATKAN CREDENTIALS GOOGLE DRIVE
========================================

STEP 1: Setup Google Cloud Project
-----------------------------------
1. Buka https://console.cloud.google.com/
2. Login dengan akun Google
3. Klik "Select a project" -> "NEW PROJECT"
4. Masukkan nama project (contoh: manga-bot-drive)
5. Klik "CREATE"

STEP 2: Enable Google Drive API
-------------------------------
1. Di Google Cloud Console, buka "APIs & Services" -> "Library"
2. Cari "Google Drive API"
3. Klik dan pilih "ENABLE"

STEP 3: Buat Service Account
----------------------------
1. Buka "APIs & Services" -> "Credentials"
2. Klik "CREATE CREDENTIALS" -> "Service account"
3. Masukkan nama service account (contoh: manga-bot-service)
4. Klik "CREATE AND CONTINUE"
5. Skip role assignment (klik "CONTINUE")
6. Skip user access (klik "DONE")

STEP 4: Generate Service Account Key
------------------------------------
1. Di halaman Credentials, klik service account yang baru dibuat
2. Buka tab "KEYS"
3. Klik "ADD KEY" -> "Create new key"
4. Pilih "JSON" format
5. Klik "CREATE"
6. File JSON akan ter-download otomatis

STEP 5: Setup Credentials di Replit
-----------------------------------
1. Buka file JSON yang ter-download
2. Copy seluruh isi file JSON
3. Di Replit, buka tab "Secrets"
4. Buat secret baru:
   - Key: GOOGLE_DRIVE_CREDENTIALS_JSON
   - Value: paste seluruh isi file JSON

STEP 6: (Opsional) Setup Folder Khusus
--------------------------------------
1. Buka Google Drive di browser
2. Buat folder baru untuk menyimpan file bot
3. Klik kanan folder -> "Share"
4. Add email service account dari step 3 dengan permission "Editor"
5. Copy ID folder dari URL (contoh: 1ABC-def_GHI2jkl)
6. Di Replit Secrets, buat secret baru:
   - Key: GOOGLE_DRIVE_FOLDER_ID
   - Value: paste folder ID

📁 STRUKTUR FILE
================
main.py                    - File utama bot
downloader.py              - Module download manga
google_drive_uploader.py   - Module upload Google Drive
keep_alive.py             - Keep bot online
requirements.txt          - Dependencies list
downloads/                - Folder temporary download
.env (opsional)          - Environment variables

🔧 ENVIRONMENT VARIABLES
========================
Wajib:
- BOT_TOKEN: Token bot dari BotFather
- GOOGLE_DRIVE_CREDENTIALS_JSON: Credentials JSON service account

Opsional:
- GOOGLE_DRIVE_FOLDER_ID: ID folder Google Drive khusus
- REPLIT_DEPLOYMENT: Set ke "1" untuk deployment mode

💻 CARA MENJALANKAN BOT
=======================
1. Pastikan semua dependencies ter-install
2. Set environment variables (BOT_TOKEN wajib)
3. Klik tombol "Run" atau jalankan: python main.py
4. Bot akan online dan siap digunakan

📝 CARA MENGGUNAKAN BOT
=======================
1. Start bot dengan /start
2. Pilih mode download (/manga atau /komik)
3. Kirim link halaman manga (bukan chapter)
   Contoh: https://komiku.org/manga/one-piece/
4. Masukkan chapter awal (contoh: 1)
5. Masukkan chapter akhir (contoh: 5)
6. Pilih mode output dan platform upload
7. Tunggu download selesai

🐛 TROUBLESHOOTING
==================
- Bot tidak respond: Check BOT_TOKEN di Secrets
- Google Drive error: Check GOOGLE_DRIVE_CREDENTIALS_JSON
- File too large: Gunakan opsi Google Drive
- Download gagal: Check link manga valid
- Memory error: Restart bot, auto cleanup aktif

⚡ FITUR ADVANCED
=================
- Auto cleanup: Hapus file otomatis
- Smart monitoring: Deteksi error dan auto recovery
- Conflict prevention: Hindari crash dari multiple request
- Progressive backoff: Smart retry mechanism
- Memory optimization: Batch processing untuk file besar

👨‍💻 DEVELOPER INFO
===================
- Platform: Replit (Python)
- Framework: pyTelegramBotAPI
- Storage: Google Drive API
- Monitoring: Built-in error recovery
- Deployment: Ready untuk 24/7 online

📞 SUPPORT
==========
Jika ada error atau butuh bantuan:
1. Check log di console Replit
2. Restart bot dengan tombol "Run"
3. Pastikan semua environment variables benar
4. Check Google Drive quota dan permissions

================================
📚 HAPPY MANGA DOWNLOADING! 🤖
================================
