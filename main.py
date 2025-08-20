import os
import shutil
import requests
from bs4 import BeautifulSoup
import telebot
from telebot import types
from downloader import download_chapter, create_pdf, download_chapter_big
from keep_alive import keep_alive
import time
import threading
import gc
import signal
import platform

TOKEN = os.getenv("BOT_TOKEN")
OUTPUT_DIR = "downloads"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Clean up downloads folder on startup
def cleanup_downloads():
    try:
        if os.path.exists(OUTPUT_DIR):
            for item in os.listdir(OUTPUT_DIR):
                item_path = os.path.join(OUTPUT_DIR, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                elif os.path.isfile(item_path):
                    os.remove(item_path)
        print("🗑️ Cleaned downloads folder on startup")
    except Exception as e:
        print(f"❌ Startup cleanup error: {e}")

cleanup_downloads()

bot = telebot.TeleBot(TOKEN)
user_state = {}
user_cancel = {}
autodemo_active = {}  # Track autodemo status for each user
autodemo_thread = {}  # Track autodemo threads

def cleanup_resources():
    """Clean up resources to prevent memory issues"""
    try:
        # Clear old user states (older than 1 hour)
        current_time = time.time()
        expired_users = []
        for chat_id, state in user_state.items():
            if current_time - state.get('timestamp', current_time) > 3600:  # 1 hour
                expired_users.append(chat_id)

        for chat_id in expired_users:
            user_state.pop(chat_id, None)
            user_cancel.pop(chat_id, None)

        # Force garbage collection
        gc.collect()
        print(f"🧹 Cleaned up {len(expired_users)} expired user sessions")
    except Exception as e:
        print(f"❌ Cleanup error: {e}")

# Run cleanup every 30 minutes
def start_cleanup_scheduler():
    def cleanup_loop():
        while True:
            time.sleep(1800)  # 30 minutes
            cleanup_resources()

    cleanup_thread = threading.Thread(target=cleanup_loop)
    cleanup_thread.daemon = True
    cleanup_thread.start()

# Aggressive auto ping and reconnect system
def start_auto_ping():
    def ping_loop():
        global bot
        consecutive_failures = 0
        max_failures = 3

        while True:
            try:
                # Less frequent pings to reduce conflicts
                time.sleep(300)  # Every 5 minutes instead of 2

                # Simple bot connection test without signal timeout
                try:
                    bot.get_me()
                    print("🏓 Auto ping sent to keep bot alive")
                    consecutive_failures = 0
                except Exception as ping_error:
                    consecutive_failures += 1
                    print(f"❌ Auto ping failed: {ping_error}")
                    
                    # If it's a 409 conflict, do webhook cleanup
                    if "409" in str(ping_error) or "conflict" in str(ping_error).lower():
                        print("🔧 409 detected in ping, cleaning webhook...")
                        cleanup_webhook_once()

                # Keep alive server ping
                try:
                    requests.get("http://0.0.0.0:8080/health", timeout=5)
                    print("🌐 Keep alive server pinged")
                except Exception as ke:
                    print(f"⚠️ Keep alive server ping failed: {ke}")

            except Exception as e:
                consecutive_failures += 1
                print(f"❌ Auto ping error #{consecutive_failures}: {e}")

                # Aggressive reconnection strategy
                if consecutive_failures >= max_failures:
                    print("🚨 Multiple ping failures detected - starting aggressive reconnect")

                    # Try multiple reconnection strategies
                    for attempt in range(5):  # 5 aggressive attempts
                        try:
                            print(f"🔄 Aggressive reconnect attempt {attempt + 1}/5...")

                            # Create new bot instance
                            bot = telebot.TeleBot(TOKEN)
                            bot.get_me()
                            print("✅ Aggressive reconnect successful!")
                            consecutive_failures = 0
                            break

                        except Exception as reconnect_error:
                            print(f"❌ Reconnect attempt {attempt + 1} failed: {reconnect_error}")
                            time.sleep(5 * (attempt + 1))  # Progressive delay

                    if consecutive_failures >= max_failures:
                        print("❌ All aggressive reconnect attempts failed")
                else:
                    # Standard retry for single failures
                    try:
                        print("🔄 Standard reconnect attempt...")
                        time.sleep(5)
                        bot.get_me()
                        print("✅ Standard reconnect successful")
                        consecutive_failures = 0
                    except:
                        print("❌ Standard reconnect failed")

    ping_thread = threading.Thread(target=ping_loop)
    ping_thread.daemon = True
    ping_thread.start()

# Simplified webhook cleanup - only on startup and errors
def cleanup_webhook_once():
    """One-time webhook cleanup to prevent conflicts"""
    global bot
    try:
        bot.delete_webhook(drop_pending_updates=True)
        print("🔧 Webhook cleaned up successfully")
        time.sleep(3)  # Wait longer for cleanup to take effect
        return True
    except Exception as e:
        print(f"🔧 Webhook cleanup failed: {e}")
        return False

# Simplified keep-alive to prevent conflicts
def start_simple_keepalive():
    def simple_loop():
        while True:
            try:
                time.sleep(600)  # Every 10 minutes only
                
                # Only ping the keep-alive server, not the bot
                try:
                    requests.get("http://0.0.0.0:8080/health", timeout=5)
                    print("🌐 Simple keep-alive ping sent")
                except Exception as e:
                    print(f"⚠️ Simple keep-alive failed: {e}")

            except Exception as e:
                print(f"❌ Simple keep-alive error: {e}")
                time.sleep(30)

    simple_thread = threading.Thread(target=simple_loop)
    simple_thread.daemon = True
    simple_thread.start()

# Enhanced error detection and auto-cleanup system
def start_comprehensive_error_monitor():
    def error_monitor_loop():
        global bot
        last_activity = time.time()
        error_count = 0
        max_errors = 5

        while True:
            try:
                time.sleep(60)  # Check every minute for errors

                # Reset error count periodically
                if error_count > 0:
                    error_count -= 1

                # 1. Check bot connectivity and auto-fix
                try:
                    bot.get_me()
                    last_activity = time.time()
                except Exception as connectivity_error:
                    error_count += 1
                    print(f"🚨 Connectivity error detected #{error_count}: {connectivity_error}")
                    auto_cleanup_all_errors()

                    # Immediate reconnect attempt
                    try:
                        bot = telebot.TeleBot(TOKEN)
                        bot.get_me()
                        print("✅ Auto-reconnect successful after connectivity error")
                        error_count = max(0, error_count - 2)  # Reward successful fix
                    except Exception as reconnect_error:
                        print(f"❌ Auto-reconnect failed: {reconnect_error}")

                # 2. Check for memory issues
                try:
                    import psutil
                    memory_percent = psutil.virtual_memory().percent
                    if memory_percent > 85:  # High memory usage
                        print(f"🚨 High memory usage detected: {memory_percent}%")
                        auto_cleanup_all_errors()
                        gc.collect()  # Force garbage collection
                        print("🧹 Memory cleanup completed")
                except ImportError:
                    pass  # psutil might not be available
                except:
                    pass

                # 3. Check for stuck user sessions
                current_time = time.time()
                stuck_users = []
                for chat_id, state in user_state.items():
                    if isinstance(state, dict):
                        session_age = current_time - state.get('timestamp', current_time)
                        if session_age > 1800:  # 30 minutes
                            stuck_users.append(chat_id)

                if stuck_users:
                    print(f"🚨 Stuck user sessions detected: {len(stuck_users)} users")
                    for chat_id in stuck_users:
                        cleanup_user_downloads(chat_id)
                        user_state.pop(chat_id, None)
                        user_cancel.pop(chat_id, None)
                        autodemo_active.pop(chat_id, None)
                    print(f"🧹 Cleaned up {len(stuck_users)} stuck sessions")

                # 4. Check download folder size
                try:
                    total_size = sum(
                        os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, dirnames, filenames in os.walk(OUTPUT_DIR)
                        for filename in filenames
                    )
                    size_mb = total_size / (1024 * 1024)
                    if size_mb > 500:  # More than 500MB
                        print(f"🚨 Large download folder detected: {size_mb:.1f}MB")
                        auto_cleanup_all_errors()
                except:
                    pass

                # 5. Check for too many errors
                if error_count >= max_errors:
                    print(f"🚨 Too many errors detected ({error_count}), performing full cleanup")
                    auto_cleanup_all_errors()
                    error_count = 0

                # 6. Check for webhook conflicts less frequently
                if error_count >= 2:  # Only check when there are multiple errors
                    try:
                        webhook_info = bot.get_webhook_info()
                        if webhook_info.url:  # Webhook is set
                            print("🚨 Webhook conflict detected, cleaning up")
                            cleanup_webhook_once()
                            print("✅ Webhook conflict resolved")
                    except Exception as webhook_error:
                        if "409" in str(webhook_error) or "conflict" in str(webhook_error).lower():
                            print(f"🚨 409 Conflict detected: {webhook_error}")
                            cleanup_webhook_once()
                            time.sleep(10)  # Wait longer after 409 errors

            except Exception as monitor_error:
                error_count += 1
                print(f"❌ Error monitor error #{error_count}: {monitor_error}")
                if error_count >= max_errors:
                    auto_cleanup_all_errors()
                    error_count = 0

    monitor_thread = threading.Thread(target=error_monitor_loop)
    monitor_thread.daemon = True
    monitor_thread.start()

def auto_cleanup_all_errors():
    """Comprehensive cleanup when any error is detected"""
    try:
        print("🧹 Starting comprehensive error cleanup...")

        # 1. Clear all user states and downloads
        all_chat_ids = list(user_state.keys()) + list(user_cancel.keys()) + list(autodemo_active.keys())
        for chat_id in set(all_chat_ids):
            try:
                cleanup_user_downloads(chat_id)
                user_state.pop(chat_id, None)
                user_cancel.pop(chat_id, None)
                if chat_id in autodemo_active:
                    autodemo_active[chat_id] = False
                autodemo_thread.pop(chat_id, None)
            except Exception as user_cleanup_error:
                print(f"⚠️ User cleanup error for {chat_id}: {user_cleanup_error}")

        # 2. Clean downloads folder completely
        try:
            if os.path.exists(OUTPUT_DIR):
                for item in os.listdir(OUTPUT_DIR):
                    item_path = os.path.join(OUTPUT_DIR, item)
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    elif os.path.isfile(item_path):
                        os.remove(item_path)
            print("🗑️ Downloads folder cleaned")
        except Exception as folder_error:
            print(f"⚠️ Folder cleanup error: {folder_error}")

        # 3. Force garbage collection
        gc.collect()

        # 4. Reset webhook
        try:
            bot.delete_webhook(drop_pending_updates=True)
            time.sleep(1)
        except:
            pass

        # 5. Clear any remaining resources
        try:
            import threading
            active_threads = threading.active_count()
            if active_threads > 10:  # Too many threads
                print(f"⚠️ High thread count: {active_threads}")
        except:
            pass

        print("✅ Comprehensive error cleanup completed")

    except Exception as cleanup_error:
        print(f"❌ Critical cleanup error: {cleanup_error}")

# Enhanced error handling and auto-restart
def start_bot_monitor():
    def monitor_loop():
        global bot
        last_activity = time.time()
        while True:
            try:
                time.sleep(600)  # Check every 10 minutes

                # Check if bot has been inactive too long
                current_time = time.time()
                if current_time - last_activity > 1800:  # 30 minutes of inactivity
                    print("⚠️ Bot inactive for 30+ minutes, sending keep-alive signal")
                    try:
                        bot.get_me()
                        last_activity = current_time
                        print("✅ Bot keep-alive successful")
                    except Exception as e:
                        print(f"❌ Bot keep-alive failed: {e}")
                        auto_cleanup_all_errors()  # Auto cleanup on keep-alive failure

                # Memory cleanup for long-running instances
                if len(user_state) > 100:  # If too many user states
                    print("🚨 Too many user states, triggering cleanup")
                    auto_cleanup_all_errors()

            except Exception as e:
                print(f"❌ Bot monitor error: {e}")
                auto_cleanup_all_errors()  # Auto cleanup on monitor error

    monitor_thread = threading.Thread(target=monitor_loop)
    monitor_thread.daemon = True
    monitor_thread.start()

# -------------------- Fungsi Ambil Data Manga --------------------
def get_manga_info(manga_url):
    resp = requests.get(manga_url, headers={"User-Agent": "Mozilla/5.0"})
    if resp.status_code != 200:
        return None, None, None

    soup = BeautifulSoup(resp.text, "html.parser")
    chapter_links = soup.select("a[href*='chapter']")
    if not chapter_links:
        return None, None, None

    first_chapter = chapter_links[0]["href"]
    if not first_chapter.startswith("http"):
        first_chapter = "https://komiku.org" + first_chapter

    slug = first_chapter.split("-chapter-")[0].replace("https://komiku.org/", "").strip("/")
    base_url = f"https://komiku.org/{slug}-chapter-{{}}/"
    manga_name = slug.split("/")[-1]

    chapter_numbers = set()
    for link in chapter_links:
        href = link["href"]
        if "-chapter-" in href:
            try:
                num = int(href.split("-chapter-")[-1].replace("/", "").split("?")[0])
                chapter_numbers.add(num)
            except:
                pass
    total_chapters = max(chapter_numbers) if chapter_numbers else None

    return base_url, manga_name, total_chapters

# -------------------- Handler /start --------------------
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    welcome_msg = (
        "👋 Selamat datang di Bot Manga Downloader! 📚\n\n"
        "Pilih mode download yang kamu inginkan:"
    )

    markup = types.InlineKeyboardMarkup()
    btn_normal = types.InlineKeyboardButton("📖 Mode Normal (/manga)", callback_data="mode_normal")
    btn_big = types.InlineKeyboardButton("🔥 Mode Komik (/komik)", callback_data="mode_big")
    markup.add(btn_normal)
    markup.add(btn_big)

    bot.send_message(chat_id, welcome_msg, reply_markup=markup)

# -------------------- Handler /manga --------------------
@bot.message_handler(commands=['manga'])
def manga_mode(message):
    chat_id = message.chat.id
    user_state[chat_id] = {"step": "link", "mode": "normal", "timestamp": time.time()}
    tutorial = (
        "📖 Mode Normal aktif! Download manga dari Komiku 📚\n\n"
        "Cara pakai:\n"
        "1️⃣ Kirim link halaman manga (bukan link chapter)\n"
        "   Contoh: https://komiku.org/manga/mairimashita-iruma-kun/\n"
        "2️⃣ Masukkan nomor chapter awal\n"
        "3️⃣ Masukkan nomor chapter akhir\n"
        "4️⃣ Pilih mau di-GABUNG jadi 1 PDF atau di-PISAH per chapter\n\n"
        "📌 Bot akan download dan kirim sesuai pilihan kamu.\n\n"
        "⚠️ Bisa hentikan download kapan saja dengan /cancel"
    )
    bot.reply_to(message, tutorial)

# -------------------- Handler Mode Selection from /start --------------------
@bot.callback_query_handler(func=lambda call: call.data in ["mode_normal", "mode_big"])
def handle_mode_selection(call):
    chat_id = call.message.chat.id
    
    # Remove the inline keyboard buttons
    try:
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
    except:
        pass

    # Answer the callback query to remove loading state
    try:
        bot.answer_callback_query(call.id)
    except:
        pass

    if call.data == "mode_normal":
        manga_mode(call.message)
    elif call.data == "mode_big":
        komik_mode(call.message)

# -------------------- Handler /cancel --------------------
@bot.message_handler(commands=['cancel'])
def cancel_download(message):
    chat_id = message.chat.id
    user_cancel[chat_id] = True

    # Clean up any existing downloads immediately
    cleanup_user_downloads(chat_id)

    bot.reply_to(message, "⛔ Download dihentikan! Semua file telah dihapus.")

def cleanup_user_downloads(chat_id):
    """Clean up all download files and folders for a specific user"""
    try:
        if chat_id in user_state and isinstance(user_state[chat_id], dict):
            manga_name = user_state[chat_id].get("manga_name", "")
            awal = user_state[chat_id].get("awal", 0)
            akhir = user_state[chat_id].get("akhir", 0)
            download_mode = user_state[chat_id].get("mode", "normal")

            # Remove chapter folders
            for ch in range(awal, akhir + 1):
                if download_mode == "big":
                    folder_ch = os.path.join(OUTPUT_DIR, f"chapter-{ch}-big")
                else:
                    folder_ch = os.path.join(OUTPUT_DIR, f"chapter-{ch}")

                if os.path.exists(folder_ch):
                    shutil.rmtree(folder_ch)
                    print(f"🗑️ Deleted folder: {folder_ch}")

        print(f"🧹 Cleanup completed for user {chat_id}")
    except Exception as e:
        print(f"❌ Cleanup error for user {chat_id}: {e}")

# -------------------- Handler /komik --------------------
@bot.message_handler(commands=['komik'])
def komik_mode(message):
    chat_id = message.chat.id
    user_state[chat_id] = {"step": "link", "mode": "big", "timestamp": time.time()}
    tutorial = (
        "🔥 Mode Komik aktif! Download gambar yang lebih panjang\n\n"
        "Cara pakai:\n"
        "1️⃣ Kirim link halaman manga (bukan link chapter)\n"
        "   Contoh: https://komiku.org/manga/the-reincarnated-assassin-is-a-genius-swordsman/\n"
        "2️⃣ Masukkan nomor chapter awal\n"
        "3️⃣ Masukkan nomor chapter akhir\n"
        "4️⃣ Pilih mau di-GABUNG jadi 1 PDF atau di-PISAH per chapter\n\n"
        "📌 Mode ini akan download gambar dengan resolusi lebih tinggi.\n"
        "⚠️ BATASAN: Maksimal 3 chapter per download\n"
        "⚠️ Bisa hentikan download kapan saja dengan /cancel"
    )
    bot.reply_to(message, tutorial)

# -------------------- Handler /autodemo --------------------
@bot.message_handler(commands=['autodemo'])
def start_autodemo(message):
    chat_id = message.chat.id

    if chat_id in autodemo_active and autodemo_active[chat_id]:
        bot.reply_to(message, "🤖 Auto demo sudah aktif! Gunakan /offautodemo untuk menghentikan.")
        return

    autodemo_active[chat_id] = True
    bot.reply_to(message, "🚀 Auto demo dimulai! (Mode hemat resource untuk mencegah forced sleep)")

    # Start autodemo thread
    def autodemo_loop():
        demo_urls = [
            "https://komiku.org/manga/mairimashita-iruma-kun/",
            "https://komiku.org/manga/one-piece/",
            "https://komiku.org/manga/naruto/",
            "https://komiku.org/manga/attack-on-titan/"
        ]
        current_url = 0
        chapter_start = 1

        try:
            while autodemo_active.get(chat_id, False):
                try:
                    # Longer initial wait to reduce resource usage
                    time.sleep(30)

                    if not autodemo_active.get(chat_id, False):
                        break

                    # Thread safety check before sending message
                    if not autodemo_active.get(chat_id, False):
                        break

                    # Send /manga command
                    try:
                        bot.send_message(chat_id, "🤖 Auto Demo: Memulai mode /manga")
                    except Exception as msg_error:
                        print(f"❌ Failed to send message: {msg_error}")
                        if not autodemo_active.get(chat_id, False):
                            break
                        continue

                    # Thread safety check before updating user_state
                    if not autodemo_active.get(chat_id, False):
                        break

                    user_state[chat_id] = {"step": "link", "mode": "normal", "timestamp": time.time()}

                    time.sleep(5)  # Increased delay

                    # Send manga URL
                    manga_url = demo_urls[current_url % len(demo_urls)]
                    try:
                        bot.send_message(chat_id, f"🤖 Auto Demo: Mengirim link\n{manga_url}")
                    except Exception as msg_error:
                        print(f"❌ Failed to send manga URL: {msg_error}")
                        if not autodemo_active.get(chat_id, False):
                            break
                        continue

                    # Process the manga URL
                    base_url, manga_name, total_chapters = get_manga_info(manga_url)
                    if base_url and autodemo_active.get(chat_id, False):
                        # Thread safety check before updating user_state
                        if not autodemo_active.get(chat_id, False):
                            break

                        user_state[chat_id].update({
                            "base_url": base_url,
                            "manga_name": manga_name,
                            "total_chapters": total_chapters,
                            "step": "awal"
                        })

                        time.sleep(5)  # Increased delay

                        if not autodemo_active.get(chat_id, False):
                            break

                        # Send chapter start
                        try:
                            bot.send_message(chat_id, f"🤖 Auto Demo: Chapter awal: {chapter_start}")
                        except Exception as msg_error:
                            print(f"❌ Failed to send chapter start: {msg_error}")
                            if not autodemo_active.get(chat_id, False):
                                break
                            continue

                        if not autodemo_active.get(chat_id, False):
                            break

                        user_state[chat_id]["awal"] = chapter_start
                        user_state[chat_id]["step"] = "akhir"

                        time.sleep(5)  # Increased delay

                        if not autodemo_active.get(chat_id, False):
                            break

                        # Send chapter end (limit to 1 chapter only for resource conservation)
                        chapter_end = min(chapter_start, total_chapters)  # Only 1 chapter
                        try:
                            bot.send_message(chat_id, f"🤖 Auto Demo: Chapter akhir: {chapter_end}")
                        except Exception as msg_error:
                            print(f"❌ Failed to send chapter end: {msg_error}")
                            if not autodemo_active.get(chat_id, False):
                                break
                            continue

                        if not autodemo_active.get(chat_id, False):
                            break

                        user_state[chat_id]["akhir"] = chapter_end
                        user_state[chat_id]["step"] = "mode"

                        time.sleep(5)  # Increased delay

                        # Auto select "pisah" mode
                        try:
                            bot.send_message(chat_id, "🤖 Auto Demo: Memilih mode PISAH per chapter")
                        except Exception as msg_error:
                            print(f"❌ Failed to send mode selection: {msg_error}")
                            if not autodemo_active.get(chat_id, False):
                                break
                            continue

                        # Start download process
                        try:
                            user_cancel[chat_id] = False
                            base_url_format = user_state[chat_id]["base_url"]
                            manga_name_demo = user_state[chat_id]["manga_name"]
                            awal = user_state[chat_id]["awal"]
                            akhir = user_state[chat_id]["akhir"]

                            try:
                                bot.send_message(chat_id, f"🤖 Auto Demo: Memulai download chapter {awal} s/d {akhir}...")
                            except Exception as msg_error:
                                print(f"❌ Failed to send download start: {msg_error}")

                            # Download in pisah mode (only 1 chapter now)
                            for ch in range(awal, akhir + 1):
                                if not autodemo_active.get(chat_id, False) or user_cancel.get(chat_id):
                                    break

                                try:
                                    bot.send_message(chat_id, f"🤖 Auto Demo: Download chapter {ch}...")
                                except Exception as msg_error:
                                    print(f"❌ Failed to send download chapter message: {msg_error}")

                                # Longer delay to reduce system load
                                time.sleep(10)

                                imgs = download_chapter(base_url_format.format(ch), ch, OUTPUT_DIR, chat_id, user_cancel)

                                if imgs and not user_cancel.get(chat_id):
                                    pdf_name = f"{manga_name_demo} chapter {ch}.pdf"
                                    pdf_path = os.path.join(OUTPUT_DIR, pdf_name)
                                    create_pdf(imgs, pdf_path)

                                    try:
                                        # Check file size for autodemo
                                        file_size = os.path.getsize(pdf_path)
                                        max_size = 50 * 1024 * 1024  # 50MB

                                        if file_size > max_size:
                                            print(f"⚠️ Auto Demo: File too large ({file_size/(1024*1024):.1f}MB), skipping")
                                            auto_delete_pdf(pdf_path, 5)
                                            continue

                                        with open(pdf_path, "rb") as pdf_file:
                                            bot.send_document(
                                                chat_id, 
                                                pdf_file, 
                                                caption=f"🤖 Auto Demo: {pdf_name} ({file_size/(1024*1024):.1f}MB)",
                                                timeout=300
                                            )
                                        print(f"✅ Auto Demo PDF sent: {pdf_name}")
                                        # Auto-delete PDF after 10 seconds
                                        auto_delete_pdf(pdf_path, 10)
                                    except Exception as upload_error:
                                        print(f"❌ Auto Demo upload error: {upload_error}")
                                        error_msg = str(upload_error)
                                        if "too large" in error_msg.lower():
                                            bot.send_message(chat_id, f"🤖 Auto Demo: File terlalu besar, dilewati")
                                        else:
                                            bot.send_message(chat_id, f"🤖 Auto Demo: Upload error")
                                        # Still delete even if upload failed
                                        auto_delete_pdf(pdf_path, 10)

                                    folder_ch = os.path.join(OUTPUT_DIR, f"chapter-{ch}")
                                    if os.path.exists(folder_ch):
                                        shutil.rmtree(folder_ch)

                            if autodemo_active.get(chat_id, False):
                                try:
                                    bot.send_message(chat_id, "🤖 Auto Demo: Selesai! Menunggu demo berikutnya...")
                                except Exception as msg_error:
                                    print(f"❌ Failed to send completion message: {msg_error}")
                                    pass

                        except Exception as download_error:
                            print(f"❌ Auto Demo download error: {download_error}")
                            try:
                                if autodemo_active.get(chat_id, False):
                                    bot.send_message(chat_id, f"🤖 Auto Demo Error: Melanjutkan ke demo berikutnya...")
                            except:
                                pass

                        # Prepare for next demo
                        current_url += 1
                        chapter_start = chapter_end + 1 if chapter_end < total_chapters - 1 else 1

                        # Wait before next demo (5 minutes) 
                        if autodemo_active.get(chat_id, False):
                            try:
                                bot.send_message(chat_id, "🤖 Auto Demo: Menunggu 5 menit untuk demo berikutnya...")
                            except:
                                pass
                            for _ in range(300):  # 5 minutes = 300 seconds
                                if not autodemo_active.get(chat_id, False):
                                    break
                                time.sleep(1)

                except Exception as inner_e:
                    print(f"❌ Autodemo inner loop error: {inner_e}")
                    try:
                        if autodemo_active.get(chat_id, False):
                            bot.send_message(chat_id, "🤖 Auto Demo: Error, mencoba lagi...")
                    except:
                        pass
                    time.sleep(30)  # Wait longer before retry
                    continue

        except Exception as main_loop_error:
            print(f"❌ Autodemo main loop error for user {chat_id}: {main_loop_error}")
            try:
                bot.send_message(chat_id, "🤖 Auto Demo dihentikan karena error")
            except:
                pass
        finally:
            # Cleanup when autodemo stops - with error handling
            try:
                if chat_id in user_state:
                    user_state.pop(chat_id, None)
                if chat_id in user_cancel:
                    user_cancel.pop(chat_id, None)
                if chat_id in autodemo_active:
                    autodemo_active[chat_id] = False
                if chat_id in autodemo_thread:
                    autodemo_thread.pop(chat_id, None)
                print(f"🤖 Autodemo stopped and cleaned up for user {chat_id}")
            except Exception as cleanup_error:
                print(f"⚠️ Autodemo cleanup error for user {chat_id}: {cleanup_error}")

    autodemo_thread[chat_id] = threading.Thread(target=autodemo_loop)
    autodemo_thread[chat_id].daemon = True
    autodemo_thread[chat_id].start()

# -------------------- Handler /offautodemo --------------------
@bot.message_handler(commands=['offautodemo'])
def stop_autodemo(message):
    chat_id = message.chat.id

    if chat_id not in autodemo_active or not autodemo_active[chat_id]:
        bot.reply_to(message, "🤖 Auto demo tidak aktif.")
        return

    # Stop autodemo gracefully
    autodemo_active[chat_id] = False
    user_cancel[chat_id] = True

    # Wait for autodemo thread to finish properly
    if chat_id in autodemo_thread:
        try:
            # Give thread time to cleanup (max 5 seconds)
            autodemo_thread[chat_id].join(timeout=5.0)
            print(f"🧹 Autodemo thread cleanup completed for user {chat_id}")
        except Exception as e:
            print(f"⚠️ Autodemo thread cleanup warning: {e}")
        finally:
            # Remove thread reference
            autodemo_thread.pop(chat_id, None)

    # Clean up any ongoing downloads
    cleanup_user_downloads(chat_id)

    # Clean up user state after thread is properly stopped
    user_state.pop(chat_id, None)
    user_cancel.pop(chat_id, None)

    bot.reply_to(message, "🛑 Auto demo dihentikan! Semua download dibatalkan dan file dihapus.")

# -------------------- Handler Pesan --------------------
@bot.message_handler(func=lambda m: True)
def handle_message(message):
    try:
        chat_id = message.chat.id
        text = message.text.strip() if message.text else ""

        if chat_id not in user_state:
            bot.reply_to(message, "Ketik /start dulu ya.")
            return

        step = user_state[chat_id].get("step", "")
        if not step:
            bot.reply_to(message, "Session bermasalah. Ketik /start untuk memulai ulang.")
            auto_cleanup_all_errors()  # Auto cleanup on session error
            return

        if step == "link":
            if not text.startswith("https://komiku.org/manga/"):
                bot.reply_to(message, "❌ Link tidak valid! Contoh:\nhttps://komiku.org/manga/mairimashita-iruma-kun/")
                return

            base_url, manga_name, total_chapters = get_manga_info(text)
            if not base_url:
                bot.reply_to(message, "❌ Gagal mengambil data manga. Pastikan link benar.")
                return

            user_state[chat_id].update({
                "base_url": base_url,
                "manga_name": manga_name,
                "total_chapters": total_chapters
            })

            user_state[chat_id]["step"] = "awal"
            bot.reply_to(message, f"📌 Masukkan chapter awal (1 - {total_chapters}):")

        elif step == "awal":
            if not text.isdigit() or int(text) <= 0:
                bot.reply_to(message, "❌ Harap masukkan angka positif untuk chapter awal.")
                return
            chapter_awal = int(text)
            total_chapters = user_state[chat_id].get("total_chapters", 999999)
            if chapter_awal > total_chapters:
                bot.reply_to(message, f"❌ Chapter awal tidak boleh lebih dari {total_chapters}.")
                return
            user_state[chat_id]["awal"] = chapter_awal
            user_state[chat_id]["step"] = "akhir"
            bot.reply_to(message, f"📌 Masukkan chapter akhir (maks {user_state[chat_id]['total_chapters']}):")

        elif step == "akhir":
            if not text.isdigit() or int(text) <= 0:
                bot.reply_to(message, "❌ Harap masukkan angka positif untuk chapter akhir.")
                return
            awal = user_state[chat_id].get("awal", 1)
            akhir = int(text)
            total = user_state[chat_id]['total_chapters']
            download_mode = user_state[chat_id].get("mode", "normal")

            if akhir < awal or akhir > total:
                bot.reply_to(message, f"❌ Chapter akhir harus >= awal dan <= {total}.")
                return

            # Check chapter limit for Komik mode
            if download_mode == "big" and (akhir - awal + 1) > 3:
                bot.reply_to(message, "❌ Mode Komik dibatasi maksimal 3 chapter!\nSilakan kurangi jumlah chapter atau gunakan mode normal.")
                return

            user_state[chat_id]["akhir"] = akhir
            user_state[chat_id]["step"] = "mode"

            markup = types.InlineKeyboardMarkup()
            btn_gabung = types.InlineKeyboardButton("📄 Gabung jadi 1 PDF", callback_data="gabung")
            btn_pisah = types.InlineKeyboardButton("📑 Pisah per Chapter", callback_data="pisah")
            markup.add(btn_gabung, btn_pisah)
            bot.send_message(chat_id, "Pilih mode download:", reply_markup=markup)

    except Exception as handler_error:
        print(f"❌ Message handler error for user {chat_id}: {handler_error}")
        auto_cleanup_all_errors()  # Auto cleanup on any handler error
        try:
            bot.send_message(chat_id, "❌ Terjadi error. Ketik /start untuk memulai ulang.")
        except:
            pass
        finally:
            # Clean up on error
            user_state.pop(chat_id, None)
            user_cancel.pop(chat_id, None)


# Auto-delete PDF function - delete after 10 seconds
def auto_delete_pdf(pdf_path, delay=10):
    """Delete PDF file after specified delay"""
    def delete_after_delay():
        time.sleep(delay)
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
                print(f"🗑️ Auto-deleted PDF: {os.path.basename(pdf_path)}")
        except Exception as e:
            print(f"❌ Auto-delete error: {e}")

    delete_thread = threading.Thread(target=delete_after_delay)
    delete_thread.daemon = True
    delete_thread.start()

# -------------------- Handler Mode Download --------------------
@bot.callback_query_handler(func=lambda call: call.data in ["gabung", "pisah"])
def handle_mode(call):
    chat_id = call.message.chat.id
    
    # Answer the callback query to remove loading state
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    
    if chat_id not in user_state:
        bot.send_message(chat_id, "❌ Session bermasalah. Ketik /start untuk memulai ulang.")
        return

    mode = call.data
    base_url = user_state[chat_id]["base_url"]
    manga_name = user_state[chat_id]["manga_name"]
    awal = user_state[chat_id]["awal"]
    akhir = user_state[chat_id]["akhir"]
    download_mode = user_state[chat_id].get("mode", "normal")

    # Remove the inline keyboard buttons
    try:
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
    except:
        pass

    user_cancel[chat_id] = False  # reset cancel flag
    bot.send_message(chat_id, f"⏳ Sedang download chapter {awal} s/d {akhir}...")

    try:
        if mode == "gabung":
            all_images = []
            for ch in range(awal, akhir + 1):
                if user_cancel.get(chat_id):
                    bot.send_message(chat_id, "❌ Download dihentikan! Membersihkan file...")
                    cleanup_user_downloads(chat_id)
                    return

                bot.send_message(chat_id, f"📥 Download chapter {ch}...")

                if download_mode == "big":
                    imgs = download_chapter_big(base_url.format(ch), ch, OUTPUT_DIR, chat_id, user_cancel)
                else:
                    imgs = download_chapter(base_url.format(ch), ch, OUTPUT_DIR, chat_id, user_cancel)

                # Check cancel status after each chapter download
                if user_cancel.get(chat_id):
                    bot.send_message(chat_id, "❌ Download dihentikan! Membersihkan file...")
                    cleanup_user_downloads(chat_id)
                    return

                all_images.extend(imgs)

            if all_images and not user_cancel.get(chat_id):
                pdf_name = f"{manga_name} chapter {awal}-{akhir}.pdf"
                pdf_path = os.path.join(OUTPUT_DIR, pdf_name)
                create_pdf(all_images, pdf_path)

                try:
                    # Check file size before upload (Telegram limit is 50MB)
                    file_size = os.path.getsize(pdf_path)
                    max_size = 50 * 1024 * 1024  # 50MB in bytes

                    if file_size > max_size:
                        size_mb = file_size / (1024 * 1024)
                        bot.send_message(chat_id, f"❌ File {pdf_name} terlalu besar ({size_mb:.1f}MB). Limit Telegram adalah 50MB.\nCoba kurangi jumlah chapter atau gunakan mode pisah.")
                        auto_delete_pdf(pdf_path, 5)
                        return

                    with open(pdf_path, "rb") as pdf_file:
                        # Add timeout protection for large files
                        bot.send_document(
                            chat_id, 
                            pdf_file, 
                            caption=f"📚 {pdf_name} ({file_size/(1024*1024):.1f}MB)",
                            timeout=300  # 5 minutes timeout
                        )
                    print(f"✅ PDF sent successfully: {pdf_name} ({file_size/(1024*1024):.1f}MB)")
                    # Auto-delete PDF after 10 seconds
                    auto_delete_pdf(pdf_path, 10)
                except Exception as upload_error:
                    print(f"❌ Upload error: {upload_error}")
                    error_msg = str(upload_error)
                    if "too large" in error_msg.lower() or "file too big" in error_msg.lower():
                        bot.send_message(chat_id, f"❌ File {pdf_name} terlalu besar untuk Telegram. Coba kurangi jumlah chapter.")
                    elif "timeout" in error_msg.lower():
                        bot.send_message(chat_id, f"⏱️ Upload {pdf_name} timeout. File mungkin terlalu besar atau koneksi lambat.")
                    else:
                        bot.send_message(chat_id, f"❌ Gagal upload {pdf_name}: {error_msg}")
                    # Still delete even if upload failed
                    auto_delete_pdf(pdf_path, 10)

                # Bersih-bersih
                for ch in range(awal, akhir + 1):
                    if download_mode == "big":
                        folder_ch = os.path.join(OUTPUT_DIR, f"chapter-{ch}-big")
                    else:
                        folder_ch = os.path.join(OUTPUT_DIR, f"chapter-{ch}")
                    if os.path.exists(folder_ch):
                        shutil.rmtree(folder_ch)

        elif mode == "pisah":
            for ch in range(awal, akhir + 1):
                if user_cancel.get(chat_id):
                    bot.send_message(chat_id, "❌ Download dihentikan! Membersihkan file...")
                    cleanup_user_downloads(chat_id)
                    return

                bot.send_message(chat_id, f"📥 Download chapter {ch}...")

                # Add small delay to reduce system load
                time.sleep(2)

                if download_mode == "big":
                    imgs = download_chapter_big(base_url.format(ch), ch, OUTPUT_DIR, chat_id, user_cancel)
                else:
                    imgs = download_chapter(base_url.format(ch), ch, OUTPUT_DIR, chat_id, user_cancel)

                # Check cancel status after each chapter download
                if user_cancel.get(chat_id):
                    bot.send_message(chat_id, "❌ Download dihentikan! Membersihkan file...")
                    cleanup_user_downloads(chat_id)
                    return

                if imgs:
                    pdf_name = f"{manga_name} chapter {ch}.pdf"
                    pdf_path = os.path.join(OUTPUT_DIR, pdf_name)
                    create_pdf(imgs, pdf_path)

                    try:
                        # Check file size before upload
                        file_size = os.path.getsize(pdf_path)
                        max_size = 50 * 1024 * 1024  # 50MB

                        if file_size > max_size:
                            size_mb = file_size / (1024 * 1024)
                            bot.send_message(chat_id, f"❌ Chapter {ch} terlalu besar ({size_mb:.1f}MB). Dilewati.")
                            auto_delete_pdf(pdf_path, 5)
                            continue

                        with open(pdf_path, "rb") as pdf_file:
                            bot.send_document(
                                chat_id, 
                                pdf_file,
                                caption=f"📖 Chapter {ch} ({file_size/(1024*1024):.1f}MB)",
                                timeout=300
                            )
                        print(f"✅ PDF sent successfully: {pdf_name}")
                        # Auto-delete PDF after 10 seconds
                        auto_delete_pdf(pdf_path, 10)
                    except Exception as upload_error:
                        print(f"❌ Upload error: {upload_error}")
                        error_msg = str(upload_error)
                        if "too large" in error_msg.lower():
                            bot.send_message(chat_id, f"❌ Chapter {ch} terlalu besar untuk Telegram.")
                        elif "timeout" in error_msg.lower():
                            bot.send_message(chat_id, f"⏱️ Upload chapter {ch} timeout.")
                        else:
                            bot.send_message(chat_id, f"❌ Gagal upload chapter {ch}: {error_msg}")
                        # Still delete even if upload failed
                        auto_delete_pdf(pdf_path, 10)

                    if download_mode == "big":
                        folder_ch = os.path.join(OUTPUT_DIR, f"chapter-{ch}-big")
                    else:
                        folder_ch = os.path.join(OUTPUT_DIR, f"chapter-{ch}")
                    if os.path.exists(folder_ch):
                        shutil.rmtree(folder_ch)
                else:
                    bot.send_message(chat_id, f"⚠️ Chapter {ch} tidak ditemukan.")

        if not user_cancel.get(chat_id):
            bot.send_message(chat_id, "✅ Selesai!")

    except Exception as e:
        print(f"❌ Download error for user {chat_id}: {e}")
        try:
            bot.send_message(chat_id, f"❌ Terjadi error: {e}")
        except:
            pass
        finally:
            # Clean up on error
            cleanup_user_downloads(chat_id)
            user_state.pop(chat_id, None)
            user_cancel.pop(chat_id, None)


# -------------------- Main --------------------
if __name__ == "__main__":
    # Check if running in deployment environment
    is_deployment = os.getenv("REPLIT_DEPLOYMENT") == "1"

    if is_deployment:
        print("🚀 Running in deployment mode - 24/7 online!")
    else:
        print("🔧 Running in development mode")

    keep_alive()
    start_cleanup_scheduler()
    start_auto_ping()
    start_simple_keepalive()  # Use simple keep-alive instead
    start_bot_monitor()
    start_comprehensive_error_monitor()
    print("🚀 Bot jalan dengan stable monitoring dan conflict prevention...")

    restart_count = 0
    max_restarts = 50  # Increased max restarts for aggressive reconnect

    while restart_count < max_restarts:
        try:
            print(f"🔄 Bot starting (attempt {restart_count + 1}/{max_restarts})")

            # Initial webhook cleanup before starting
            success = cleanup_webhook_once()
            if success:
                print("🔧 Initial webhook cleanup successful")
            else:
                print("🔧 Initial webhook cleanup failed, continuing anyway")

            if is_deployment:
                # Stable settings for deployment to prevent conflicts
                bot.infinity_polling(
                    timeout=60,           # Longer timeout to prevent conflicts
                    long_polling_timeout=30,  # Standard polling timeout
                    none_stop=True,       # Don't stop on errors
                    interval=2,           # Check every 2 seconds to reduce conflicts
                    allowed_updates=None  # Process all updates
                )
            else:
                # Stable development settings
                bot.infinity_polling(
                    timeout=30,
                    long_polling_timeout=20,
                    none_stop=True,
                    interval=1             # 1 second interval for development
                )

        except KeyboardInterrupt:
            print("🛑 Bot stopped by user")
            break
        except Exception as e:
            print(f"❌ Bot error (attempt {restart_count + 1}): {e}")
            auto_cleanup_all_errors()  # Auto cleanup on any bot error

            # Immediate aggressive reconnect attempts
            for immediate_retry in range(3):
                try:
                    print(f"🔥 Immediate reconnect attempt {immediate_retry + 1}/3")
                    time.sleep(2)  # Very short wait

                    # Reinitialize bot
                    bot = telebot.TeleBot(TOKEN)
                    bot.get_me()
                    print("✅ Immediate reconnect successful!")
                    restart_count = max(0, restart_count - 2)  # Reduce restart count on immediate success
                    break

                except Exception as immediate_error:
                    print(f"❌ Immediate reconnect {immediate_retry + 1} failed: {immediate_error}")
            else:
                # If immediate reconnects failed, do standard restart
                restart_count += 1

            # Shorter progressive backoff for faster recovery
            wait_time = min(30, 2 * restart_count)  # Max 30 seconds wait

            # Clear states on error to prevent memory issues
            try:
                user_state.clear()
                user_cancel.clear()
                autodemo_active.clear()
                print("🧹 Cleared all user states after error")
            except:
                pass

            if restart_count < max_restarts:
                print(f"🔄 Aggressive restart in {wait_time} seconds...")
                time.sleep(wait_time)

                # Multiple reinitialize attempts
                for init_attempt in range(3):
                    try:
                        bot = telebot.TeleBot(TOKEN)
                        bot.get_me()
                        print("✅ Bot reinitialization successful")
                        restart_count = max(0, restart_count - 1)  # Reward successful init
                        break
                    except Exception as init_error:
                        print(f"❌ Init attempt {init_attempt + 1} failed: {init_error}")
                        time.sleep(3)

            else:
                print("❌ Max restart attempts reached. Attempting final recovery...")

                # Final recovery attempt with completely new bot instance
                try:
                    time.sleep(10)
                    bot = telebot.TeleBot(TOKEN)
                    bot.get_me()
                    print("✅ Final recovery successful! Resetting restart counter.")
                    restart_count = 0  # Reset counter for final recovery
                    continue
                except:
                    print("❌ Final recovery failed. Bot stopped.")
                    break

    print("🏁 Bot execution finished")