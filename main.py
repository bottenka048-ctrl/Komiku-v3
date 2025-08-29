
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

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Environment variables loaded from .env file")
except ImportError:
    print("⚠️ python-dotenv not installed, using system environment variables")

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

# -------------------- Auto cleanup function --------------------
def auto_cleanup_all_errors():
    """Comprehensive cleanup function for all errors"""
    try:
        # Clean downloads folder
        if os.path.exists(OUTPUT_DIR):
            for item in os.listdir(OUTPUT_DIR):
                item_path = os.path.join(OUTPUT_DIR, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    elif os.path.isfile(item_path):
                        os.remove(item_path)
                except:
                    pass
        
        # Clear user states
        user_state.clear()
        user_cancel.clear()
        autodemo_active.clear()
        
        # Force garbage collection
        gc.collect()
        print("🧹 Auto cleanup completed")
    except Exception as e:
        print(f"❌ Auto cleanup error: {e}")

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

# Smart auto ping system optimized for Google Cloud Shell - ping setiap 1 menit
def start_smart_auto_ping():
    def ping_loop():
        global bot
        consecutive_failures = 0
        max_failures = 3
        
        # Detect if running in Google Cloud Shell
        is_google_shell = os.getenv('CLOUD_SHELL') or os.getenv('DEVSHELL_PROJECT_ID') or 'cloudshell' in os.getenv('HOSTNAME', '').lower()
        if is_google_shell:
            print("🌩️ Google Cloud Shell detected - using 1 minute ping interval")
            ping_interval = 60  # 1 minute for Google Cloud Shell
        else:
            print("🖥️ Regular environment - using 3 minute ping interval")
            ping_interval = 180  # 3 minutes for other environments

        while True:
            try:
                # Auto ping with dynamic interval
                time.sleep(ping_interval)

                # Check if any autodemo is active
                autodemo_running = any(autodemo_active.values())

                if autodemo_running:
                    print("🤖 Autodemo aktif - melewati auto ping untuk mencegah konflik")
                    continue

                # Simple bot connection test
                try:
                    bot.get_me()
                    interval_msg = "1 min" if ping_interval == 60 else "3 min"
                    print(f"🏓 Auto ping sent to keep bot alive ({interval_msg} interval)")
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
                    response = requests.get("http://0.0.0.0:8080/health", timeout=5)
                    if response.status_code == 200:
                        print("🌐 Keep alive server pinged successfully")
                    else:
                        print(f"⚠️ Keep alive server responded with status {response.status_code}")
                except Exception as ke:
                    print(f"⚠️ Keep alive server ping failed: {ke}")

            except Exception as e:
                consecutive_failures += 1
                print(f"❌ Auto ping error #{consecutive_failures}: {e}")

                # Only attempt reconnection if no autodemo is running
                autodemo_running = any(autodemo_active.values())
                if not autodemo_running and consecutive_failures >= max_failures:
                    print("🚨 Multiple ping failures detected - starting reconnect")

                    # Try reconnection
                    for attempt in range(3):  # Reduced attempts to prevent conflicts
                        try:
                            print(f"🔄 Reconnect attempt {attempt + 1}/3...")

                            # Create new bot instance
                            bot = telebot.TeleBot(TOKEN)
                            bot.get_me()
                            print("✅ Reconnect successful!")
                            consecutive_failures = 0
                            break

                        except Exception as reconnect_error:
                            print(f"❌ Reconnect attempt {attempt + 1} failed: {reconnect_error}")
                            time.sleep(3 * (attempt + 1))

                    if consecutive_failures >= max_failures:
                        print("❌ All reconnect attempts failed")

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

# -------------------- Fungsi Ambil Data Manga --------------------
def get_manga_info(manga_url):
    resp = requests.get(manga_url, headers={"User-Agent": "Mozilla/5.0"})
    if resp.status_code != 200:
        return None, None, None, None

    soup = BeautifulSoup(resp.text, "html.parser")
    chapter_links = soup.select("a[href*='chapter']")
    if not chapter_links:
        return None, None, None, None

    first_chapter = chapter_links[0]["href"]
    if not first_chapter.startswith("http"):
        first_chapter = "https://komiku.org" + first_chapter

    slug = first_chapter.split("-chapter-")[0].replace("https://komiku.org/", "").strip("/")
    base_url = f"https://komiku.org/{slug}-chapter-{{}}/"
    manga_name = slug.split("/")[-1]

    chapter_numbers = set()
    chapter_list = []  # Store all chapter identifiers
    for link in chapter_links:
        href = link["href"]
        if "-chapter-" in href:
            try:
                chapter_str = href.split("-chapter-")[-1].replace("/", "").split("?")[0]
                chapter_list.append(chapter_str)
                # Try to parse as number for sorting, skip if contains special chars
                try:
                    if '.' in chapter_str and '-' not in chapter_str:
                        num = float(chapter_str)
                    elif '-' not in chapter_str and not any(c.isalpha() for c in chapter_str):
                        num = int(chapter_str)
                    else:
                        # Skip chapters with special formatting like "160-5" or "extra"
                        continue
                    chapter_numbers.add(num)
                except ValueError:
                    # Skip chapters that can't be parsed as numbers
                    continue
            except:
                pass

    # Sort chapters properly (handle both int and float)
    sorted_chapters = sorted(chapter_list, key=lambda x: float(x) if '.' in x and '-' not in x else (int(x) if '-' not in x and not any(c.isalpha() for c in x) else float('inf')))
    total_chapters = max(chapter_numbers) if chapter_numbers else None

    return base_url, manga_name, total_chapters, sorted_chapters

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

def cleanup_user_downloads(chat_id):
    """Clean up all download files and folders for a specific user"""
    try:
        if chat_id in user_state and isinstance(user_state[chat_id], dict):
            manga_name = user_state[chat_id].get("manga_name", "")
            awal_str = user_state[chat_id].get("awal", "1")
            akhir_str = user_state[chat_id].get("akhir", "1")
            available_chapters = user_state[chat_id].get("available_chapters", [])
            download_mode = user_state[chat_id].get("mode", "normal")

            # Determine the chapters that were intended for download based on the state
            chapters_to_cleanup = []
            if available_chapters and awal_str in available_chapters and akhir_str in available_chapters:
                awal_index = available_chapters.index(awal_str)
                akhir_index = available_chapters.index(akhir_str)
                chapters_to_cleanup = available_chapters[awal_index:akhir_index + 1]
            elif "chapters_to_download" in user_state[chat_id]:
                # If 'chapters_to_download' is available (after fix), use that
                chapters_to_download_from_state = user_state[chat_id]["chapters_to_download"]
                chapters_to_cleanup = chapters_to_download_from_state

            for ch_str in chapters_to_cleanup:
                if download_mode == "big":
                    folder_ch = os.path.join(OUTPUT_DIR, f"chapter-{ch_str}-big")
                else:
                    folder_ch = os.path.join(OUTPUT_DIR, f"chapter-{ch_str}")

                if os.path.exists(folder_ch):
                    shutil.rmtree(folder_ch)
                    print(f"🗑️ Deleted folder: {folder_ch}")

        print(f"🧹 Cleanup completed for user {chat_id}")
    except Exception as e:
        print(f"❌ Cleanup error for user {chat_id}: {e}")

# -------------------- Handler /start --------------------
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    welcome_msg = (
        "👋 Selamat datang di Bot Manga Downloader! 📚\n\n"
        "🔧 Commands tersedia:\n"
        "• /clear - Hapus pesan bot (file tetap tersimpan)\n"
        "• /cancel - Hentikan download\n\n"
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
        "⚠️ Commands: /cancel (hentikan download) | /clear (hapus pesan)"
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

# -------------------- Handler /clear --------------------
@bot.message_handler(commands=['clear'])
def clear_messages(message):
    chat_id = message.chat.id
    
    try:
        # Send confirmation message
        confirm_msg = bot.send_message(chat_id, "🧹 Menghapus pesan bot 40 JAM ke belakang... (file akan tetap tersimpan)")
        
        # Get current message ID to work backwards
        current_msg_id = message.message_id
        deleted_count = 0
        max_attempts = 800  # Reduced for 40 hour coverage
        
        # Strategy 1: Delete recent messages going backwards (40 hour range)
        print(f"🧹 Starting 40-hour message cleanup for chat {chat_id}")
        
        for i in range(max_attempts):
            try:
                msg_id_to_delete = current_msg_id - i
                if msg_id_to_delete <= 0:
                    break
                    
                # Try to delete the message
                bot.delete_message(chat_id, msg_id_to_delete)
                deleted_count += 1
                
                # Adaptive delay based on progress
                if deleted_count % 50 == 0:
                    time.sleep(0.5)  # Longer pause every 50 deletions
                else:
                    time.sleep(0.02)  # Very fast for most deletions
                
            except Exception as delete_error:
                error_str = str(delete_error).lower()
                if "too many requests" in error_str:
                    # If rate limited, wait longer and continue
                    time.sleep(3)
                    continue
                else:
                    # Skip other errors and continue
                    continue
        
        # Strategy 2: Extended backward search (40 hour coverage)
        older_start = current_msg_id - max_attempts
        for i in range(400):  # Try 400 more older messages for 40 hours
            try:
                msg_id_to_delete = older_start - i
                if msg_id_to_delete <= 0:
                    break
                    
                bot.delete_message(chat_id, msg_id_to_delete)
                deleted_count += 1
                time.sleep(0.03)
                
            except Exception:
                continue
        
        # Strategy 3: Forward sweep from 40-hour point
        hours_40_start = max(1, current_msg_id - 2000)  # Go back approximately 40 hours
        
        # Process in chunks to avoid timeouts
        chunk_size = 50
        for chunk_start in range(hours_40_start, current_msg_id, chunk_size):
            chunk_end = min(chunk_start + chunk_size, current_msg_id)
            
            for msg_id in range(chunk_start, chunk_end):
                try:
                    bot.delete_message(chat_id, msg_id)
                    deleted_count += 1
                    time.sleep(0.02)
                    
                    # Progress check
                    if deleted_count > 500:
                        print(f"🧹 Deleted {deleted_count} messages, continuing...")
                        
                except Exception:
                    continue
            
            # Small pause between chunks
            time.sleep(0.3)
            
            # Stop if we've deleted enough for 40 hours
            if deleted_count > 800:
                break
        
        # Strategy 4: Random sampling for missed messages (40 hour range)
        import random
        for _ in range(200):
            try:
                random_msg_id = random.randint(max(1, current_msg_id - 2000), current_msg_id)
                bot.delete_message(chat_id, random_msg_id)
                deleted_count += 1
                time.sleep(0.01)
            except Exception:
                continue
        
        # Send final status
        final_msg = bot.send_message(chat_id, f"✅ PEMBERSIHAN 40 JAM SELESAI! Berhasil menghapus {deleted_count} pesan!")
        
        # Auto-delete the confirmation and final messages after 5 seconds
        def auto_delete_clear_messages():
            time.sleep(5)
            try:
                bot.delete_message(chat_id, confirm_msg.message_id)
            except:
                pass
            try:
                bot.delete_message(chat_id, final_msg.message_id)
            except:
                pass
            try:
                # Also try to delete the original /clear command
                bot.delete_message(chat_id, message.message_id)
            except:
                pass
        
        clear_thread = threading.Thread(target=auto_delete_clear_messages)
        clear_thread.daemon = True
        clear_thread.start()
        
        print(f"✅ Aggressive cleanup completed for chat {chat_id}: {deleted_count} messages deleted")
        
    except Exception as clear_error:
        print(f"❌ Clear messages error: {clear_error}")
        try:
            bot.send_message(chat_id, "❌ Terjadi error saat menghapus pesan. Mungkin ada batasan dari Telegram.")
        except:
            pass

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
        "⚠️ Commands: /cancel (hentikan download) | /clear (hapus pesan)"
    )
    bot.reply_to(message, tutorial)

# -------------------- Handler /autodemo --------------------
@bot.message_handler(commands=['autodemo'])
def start_autodemo(message):
    chat_id = message.chat.id

    if chat_id in autodemo_active and autodemo_active[chat_id]:
        bot.reply_to(message, "🤖 Auto demo sudah aktif! Gunakan /offautodemo untuk menghentikan.")
        return

    # Check if any other autodemo is running to prevent crashes
    if any(autodemo_active.values()):
        bot.reply_to(message, "⚠️ Ada autodemo lain yang sedang berjalan. Hanya 1 autodemo diizinkan untuk mencegah crash.")
        return

    # Stop existing thread if any
    if chat_id in autodemo_thread and autodemo_thread[chat_id].is_alive():
        autodemo_active[chat_id] = False
        autodemo_thread[chat_id].join(timeout=2)

    autodemo_active[chat_id] = True
    bot.reply_to(message, "🚀 Auto demo dimulai! (Hanya 1 autodemo aktif untuk stabilitas)")

    # Start autodemo thread with better error handling
    def autodemo_loop():
        demo_urls = [
            "https://komiku.org/manga/mairimashita-iruma-kun/",
            "https://komiku.org/manga/one-piece/",
            "https://komiku.org/manga/naruto/",
            "https://komiku.org/manga/attack-on-titan/"
        ]
        current_url_index = 0
        chapter_start_num = 1

        try:
            while autodemo_active.get(chat_id, False):
                try:
                    # Longer initial wait to reduce resource usage
                    time.sleep(30)

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

                    user_state[chat_id] = {"step": "link", "mode": "normal", "timestamp": time.time()}

                    time.sleep(5)  # Increased delay

                    # Send manga URL
                    manga_url = demo_urls[current_url_index % len(demo_urls)]
                    try:
                        bot.send_message(chat_id, f"🤖 Auto Demo: Mengirim link\n{manga_url}")
                    except Exception as msg_error:
                        print(f"❌ Failed to send manga URL: {msg_error}")
                        if not autodemo_active.get(chat_id, False):
                            break
                        continue

                    # Process the manga URL
                    base_url, manga_name, total_chapters, sorted_chapters = get_manga_info(manga_url)
                    if base_url and manga_name and sorted_chapters and autodemo_active.get(chat_id, False):
                        user_state[chat_id].update({
                            "base_url": base_url,
                            "manga_name": manga_name,
                            "total_chapters": total_chapters,
                            "available_chapters": sorted_chapters,
                            "step": "awal"
                        })

                        time.sleep(5)  # Increased delay

                        # Use first available chapter instead of hardcoded numbers
                        if sorted_chapters:
                            first_chapter = sorted_chapters[0]
                            user_state[chat_id]["awal"] = first_chapter
                            user_state[chat_id]["step"] = "akhir"

                            time.sleep(5)  # Increased delay

                            if not autodemo_active.get(chat_id, False):
                                break

                            # Send chapter end (use same chapter for single chapter download)
                            chapter_end = first_chapter
                            try:
                                bot.send_message(chat_id, f"🤖 Auto Demo: Chapter awal: {first_chapter}")
                            except Exception as msg_error:
                                print(f"❌ Failed to send chapter start: {msg_error}")
                                if not autodemo_active.get(chat_id, False):
                                    break
                                continue

                            time.sleep(5)  # Increased delay

                            try:
                                bot.send_message(chat_id, f"🤖 Auto Demo: Chapter akhir: {chapter_end}")
                            except Exception as msg_error:
                                print(f"❌ Failed to send chapter end: {msg_error}")
                                if not autodemo_active.get(chat_id, False):
                                    break
                                continue

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
                                for ch in [awal]: # Iterate only for the single chapter
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

                                # Prepare for next demo
                                current_url_index += 1
                                chapter_start_num = 1 # Reset for next demo

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

                            except Exception as download_error:
                                print(f"❌ Download process error: {download_error}")
                                try:
                                    if autodemo_active.get(chat_id, False):
                                        bot.send_message(chat_id, "🤖 Auto Demo: Error saat download, mencoba berikutnya...")
                                except:
                                    pass

                        else: # Handle case where sorted_chapters is empty
                            print(f"❌ Failed to get manga info for {manga_url}")
                            try:
                                if autodemo_active.get(chat_id, False):
                                    bot.send_message(chat_id, "🤖 Auto Demo: Error mengambil data manga, mencoba berikutnya...")
                            except:
                                pass
                            continue  # Skip to next manga URL
                            
                    else: # Handle case where get_manga_info failed
                        print(f"❌ Failed to get manga info for {manga_url}")
                        try:
                            if autodemo_active.get(chat_id, False):
                                bot.send_message(chat_id, "🤖 Auto Demo: Error mengambil data manga, mencoba berikutnya...")
                        except:
                            pass
                        continue  # Skip to next manga URL

                except Exception as inner_e:
                    print(f"❌ Autodemo inner loop error: {inner_e}")
                    try:
                        if autodemo_active.get(chat_id, False):
                            bot.send_message(chat_id, "🤖 Auto Demo: Error, menunggu sebelum retry...")
                    except:
                        pass

                    # Longer wait on error to prevent rapid crashes
                    for wait_second in range(60):  # 1 minute wait
                        if not autodemo_active.get(chat_id, False):
                            break
                        time.sleep(1)
                    continue

        except Exception as main_loop_error:
            print(f"❌ Autodemo main loop error for user {chat_id}: {main_loop_error}")
            try:
                if autodemo_active.get(chat_id, False):
                    bot.send_message(chat_id, "🤖 Auto Demo dihentikan karena error")
            except:
                pass
        finally:
            # Enhanced cleanup when autodemo stops
            try:
                print(f"🧹 Starting autodemo cleanup for user {chat_id}")

                # Stop autodemo flag first
                if chat_id in autodemo_active:
                    autodemo_active[chat_id] = False

                # Clean user states
                if chat_id in user_state:
                    user_state.pop(chat_id, None)
                if chat_id in user_cancel:
                    user_cancel.pop(chat_id, None)

                # Clean any downloads
                cleanup_user_downloads(chat_id)

                # Remove thread reference
                if chat_id in autodemo_thread:
                    autodemo_thread.pop(chat_id, None)

                # Force garbage collection
                gc.collect()
                print(f"✅ Autodemo cleanup completed for user {chat_id}")

            except Exception as cleanup_error:
                print(f"⚠️ Autodemo cleanup error for user {chat_id}: {cleanup_error}")

    # Create and start thread with better naming
    autodemo_thread[chat_id] = threading.Thread(
        target=autodemo_loop,
        name=f"AutoDemo-{chat_id}"
    )
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

            base_url, manga_name, total_chapters, sorted_chapters = get_manga_info(text)
            if not base_url:
                bot.reply_to(message, "❌ Gagal mengambil data manga. Pastikan link benar.")
                return

            user_state[chat_id].update({
                "base_url": base_url,
                "manga_name": manga_name,
                "total_chapters": total_chapters,
                "available_chapters": sorted_chapters
            })

            user_state[chat_id]["step"] = "awal"

            bot.reply_to(message, f"✅ Manga berhasil diambil: **{manga_name}**\nTotal chapter: {total_chapters if total_chapters else 'Tidak diketahui'}\n\nMasukkan chapter awal (bisa decimal seperti 1.5):")

        elif step == "awal":
            # Normalize input - convert simple numbers to match available format
            chapter_awal_str = text.strip()
            available_chapters = user_state[chat_id].get("available_chapters", [])

            # Try to find matching chapter in available list
            matched_chapter = None

            # First, try exact match
            if chapter_awal_str in available_chapters:
                matched_chapter = chapter_awal_str
            else:
                # Try to match with different formats
                try:
                    # Convert input to number for comparison
                    if '.' in chapter_awal_str and '-' not in chapter_awal_str:
                        input_num = float(chapter_awal_str)
                    elif '-' not in chapter_awal_str and not any(c.isalpha() for c in chapter_awal_str):
                        input_num = int(chapter_awal_str)
                    else:
                        bot.reply_to(message, "❌ Format chapter tidak valid. Hindari karakter khusus seperti '-' atau huruf.")
                        return

                    if input_num <= 0:
                        bot.reply_to(message, "❌ Chapter harus lebih dari 0.")
                        return

                    # Find matching chapter in available list
                    for ch in available_chapters:
                        try:
                            if '.' in ch and '-' not in ch:
                                ch_num = float(ch)
                            elif '-' not in ch and not any(c.isalpha() for c in ch):
                                ch_num = int(ch)
                            else:
                                continue

                            if ch_num == input_num:
                                matched_chapter = ch
                                break
                        except ValueError:
                            continue

                except ValueError:
                    bot.reply_to(message, "❌ Format chapter tidak valid. Contoh: 1, 9, 1.5, 7.2")
                    return

            if not matched_chapter:
                # Show available chapters for user reference
                sample_chapters = available_chapters[:15] if len(available_chapters) > 15 else available_chapters
                bot.reply_to(message, f"❌ Chapter {chapter_awal_str} tidak tersedia.\n\nChapter tersedia: {', '.join(sample_chapters)}")
                return

            user_state[chat_id]["awal"] = matched_chapter
            user_state[chat_id]["step"] = "akhir"
            bot.reply_to(message, f"✅ Chapter awal: {matched_chapter}\n📌 Masukkan chapter akhir (contoh: 9, 15.5):")

        elif step == "akhir":
            # Normalize input - convert simple numbers to match available format
            chapter_akhir_str = text.strip()
            available_chapters = user_state[chat_id].get("available_chapters", [])

            # Try to find matching chapter in available list
            matched_chapter = None

            # First, try exact match
            if chapter_akhir_str in available_chapters:
                matched_chapter = chapter_akhir_str
            else:
                # Try to match with different formats
                try:
                    # Convert input to number for comparison
                    if '.' in chapter_akhir_str and '-' not in chapter_akhir_str:
                        input_num = float(chapter_akhir_str)
                    elif '-' not in chapter_akhir_str and not any(c.isalpha() for c in chapter_akhir_str):
                        input_num = int(chapter_akhir_str)
                    else:
                        bot.reply_to(message, "❌ Format chapter tidak valid. Hindari karakter khusus seperti '-' atau huruf.")
                        return

                    if input_num <= 0:
                        bot.reply_to(message, "❌ Chapter harus lebih dari 0.")
                        return

                    # Find matching chapter in available list
                    for ch in available_chapters:
                        try:
                            if '.' in ch and '-' not in ch:
                                ch_num = float(ch)
                            elif '-' not in ch and not any(c.isalpha() for c in ch):
                                ch_num = int(ch)
                            else:
                                continue

                            if ch_num == input_num:
                                matched_chapter = ch
                                break
                        except ValueError:
                            continue

                except ValueError:
                    bot.reply_to(message, "❌ Format chapter tidak valid. Contoh: 1, 9, 1.5, 7.2")
                    return

            if not matched_chapter:
                # Show available chapters for user reference
                sample_chapters = available_chapters[:15] if len(available_chapters) > 15 else available_chapters
                bot.reply_to(message, f"❌ Chapter {chapter_akhir_str} tidak tersedia.\n\nChapter tersedia: {', '.join(sample_chapters)}")
                return

            awal_str = user_state[chat_id].get("awal", "1")
            download_mode = user_state[chat_id].get("mode", "normal")

            # Find positions in available chapters list
            try:
                awal_index = available_chapters.index(awal_str)
                akhir_index = available_chapters.index(matched_chapter)
            except ValueError:
                bot.reply_to(message, "❌ Error dalam menentukan posisi chapter.")
                return

            if akhir_index < awal_index:
                bot.reply_to(message, f"❌ Chapter akhir harus berada setelah atau sama dengan chapter awal ({awal_str}).")
                return

            # Calculate actual chapter count based on available chapters
            chapter_count = akhir_index - awal_index + 1
            chapters_to_download = available_chapters[awal_index:akhir_index + 1]

            # Remove duplicates while preserving order
            unique_chapters = []
            seen = set()
            for ch in chapters_to_download:
                if ch not in seen:
                    unique_chapters.append(ch)
                    seen.add(ch)

            chapters_to_download = unique_chapters
            chapter_count = len(chapters_to_download)

            # Check chapter limit for Komik mode
            if download_mode == "big" and chapter_count > 3:
                bot.reply_to(message, "❌ Mode Komik dibatasi maksimal 3 chapter!\nSilakan kurangi jumlah chapter atau gunakan mode pisah.")
                return

            user_state[chat_id]["akhir"] = matched_chapter
            user_state[chat_id]["chapters_to_download"] = chapters_to_download  # Store the actual chapters to download
            user_state[chat_id]["step"] = "mode"

            markup = types.InlineKeyboardMarkup()
            btn_gabung = types.InlineKeyboardButton("📄 Gabung jadi 1 PDF", callback_data="gabung")
            btn_pisah = types.InlineKeyboardButton("📑 Pisah per Chapter", callback_data="pisah")
            markup.add(btn_gabung, btn_pisah)

            # Show which chapters will be downloaded
            if chapter_count <= 10:
                chapters_preview = ', '.join(chapters_to_download)
            else:
                chapters_preview = f"{', '.join(chapters_to_download[:5])}, ..., {', '.join(chapters_to_download[-3:])}"

            bot.send_message(chat_id, f"📊 Chapter yang akan didownload ({chapter_count} chapter):\n{chapters_preview}\n\nPilih mode download:", reply_markup=markup)

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
    chapters_to_download = user_state[chat_id].get("chapters_to_download", []) # Use stored unique chapters

    # Remove the inline keyboard buttons
    try:
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
    except:
        pass

    user_cancel[chat_id] = False  # reset cancel flag
    bot.send_message(chat_id, f"⏳ Sedang download chapter {' & '.join(chapters_to_download)}...")

    try:
        if mode == "gabung":
            all_images = []

            for ch_str in chapters_to_download:
                if user_cancel.get(chat_id):
                    bot.send_message(chat_id, "❌ Download dihentikan! Membersihkan file...")
                    cleanup_user_downloads(chat_id)
                    return

                bot.send_message(chat_id, f"📥 Download chapter {ch_str}...")

                if download_mode == "big":
                    imgs = download_chapter_big(base_url.format(ch_str), ch_str, OUTPUT_DIR, chat_id, user_cancel)
                else:
                    imgs = download_chapter(base_url.format(ch_str), ch_str, OUTPUT_DIR, chat_id, user_cancel)

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
                for ch in chapters_to_download:
                    if download_mode == "big":
                        folder_ch = os.path.join(OUTPUT_DIR, f"chapter-{ch}-big")
                    else:
                        folder_ch = os.path.join(OUTPUT_DIR, f"chapter-{ch}")
                    if os.path.exists(folder_ch):
                        shutil.rmtree(folder_ch)

        elif mode == "pisah":
            for ch_str in chapters_to_download:
                if user_cancel.get(chat_id):
                    bot.send_message(chat_id, "❌ Download dihentikan! Membersihkan file...")
                    cleanup_user_downloads(chat_id)
                    return

                bot.send_message(chat_id, f"📥 Download chapter {ch_str}...")

                # Add small delay to reduce system load
                time.sleep(2)

                if download_mode == "big":
                    imgs = download_chapter_big(base_url.format(ch_str), ch_str, OUTPUT_DIR, chat_id, user_cancel)
                else:
                    imgs = download_chapter(base_url.format(ch_str), ch_str, OUTPUT_DIR, chat_id, user_cancel)

                # Check cancel status after each chapter download
                if user_cancel.get(chat_id):
                    bot.send_message(chat_id, "❌ Download dihentikan! Membersihkan file...")
                    cleanup_user_downloads(chat_id)
                    return

                if imgs:
                    pdf_name = f"{manga_name} chapter {ch_str}.pdf"
                    pdf_path = os.path.join(OUTPUT_DIR, pdf_name)
                    create_pdf(imgs, pdf_path)

                    try:
                        # Check file size before upload
                        file_size = os.path.getsize(pdf_path)
                        max_size = 50 * 1024 * 1024  # 50MB

                        if file_size > max_size:
                            size_mb = file_size / (1024 * 1024)
                            bot.send_message(chat_id, f"❌ Chapter {ch_str} terlalu besar ({size_mb:.1f}MB). Dilewati.")
                            auto_delete_pdf(pdf_path, 5)
                            continue

                        with open(pdf_path, "rb") as pdf_file:
                            bot.send_document(
                                chat_id,
                                pdf_file,
                                caption=f"📖 Chapter {ch_str} ({file_size/(1024*1024):.1f}MB)",
                                timeout=300
                            )
                        print(f"✅ PDF sent successfully: {pdf_name}")
                        # Auto-delete PDF after 10 seconds
                        auto_delete_pdf(pdf_path, 10)
                    except Exception as upload_error:
                        print(f"❌ Upload error: {upload_error}")
                        error_msg = str(upload_error)
                        if "too large" in error_msg.lower():
                            bot.send_message(chat_id, f"❌ Chapter {ch_str} terlalu besar untuk Telegram.")
                        elif "timeout" in error_msg.lower():
                            bot.send_message(chat_id, f"⏱️ Upload chapter {ch_str} timeout.")
                        else:
                            bot.send_message(chat_id, f"❌ Gagal upload chapter {ch_str}: {error_msg}")
                        # Still delete even if upload failed
                        auto_delete_pdf(pdf_path, 10)

                    # Cleanup chapter folder after successful upload
                    if download_mode == "big":
                        folder_ch = os.path.join(OUTPUT_DIR, f"chapter-{ch_str}-big")
                    else:
                        folder_ch = os.path.join(OUTPUT_DIR, f"chapter-{ch_str}")
                    if os.path.exists(folder_ch):
                        shutil.rmtree(folder_ch)
                else:
                    bot.send_message(chat_id, f"⚠️ Chapter {ch_str} tidak ditemukan.")

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
    start_smart_auto_ping()  # Use smart auto ping instead
    start_simple_keepalive()
    start_comprehensive_error_monitor()
    print("🚀 Bot jalan dengan smart monitoring dan conflict prevention...")

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
