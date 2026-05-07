import os
import re
import yt_dlp
import json
import time
import threading
from pathlib import Path
from typing import Optional
import requests
from rubpy import Client as RubikaClient

# ========== تنظیمات ==========
BALE_TOKEN = "توکن_ربات_خود_را_اینجا_بگذارید"  # توکنی که از @BotFather بله گرفتی
BALE_API_URL = "https://tapi.bale.ai"
DOWNLOAD_PATH = "/root/youtube_downloads"

# تنظیمات روبیکا
RUBIKA_SESSION = "rubika_session"
RUBIKA_TARGET = "me"
# =============================

os.makedirs(DOWNLOAD_PATH, exist_ok=True)

# دیکشنری برای نگهداری وضعیت کاربران
user_states = {}


class BaleBot:
    """کلاس ساده برای ارتباط با API بله"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"{BALE_API_URL}/bot{token}"
        self.offset = 0
        self.timeout = 30
    
    def _post(self, method: str, data: dict = None):
        """ارسال درخواست به API بله"""
        url = f"{self.base_url}/{method}"
        try:
            if data is None:
                data = {}
            response = requests.post(url, json=data, timeout=self.timeout)
            return response.json()
        except Exception as e:
            print(f"خطا در درخواست {method}: {e}")
            return None
    
    def get_updates(self):
        """دریافت آپدیت‌ها"""
        data = {
            "offset": self.offset,
            "timeout": self.timeout,
            "allowed_updates": ["message", "callback_query"]
        }
        result = self._post("getUpdates", data)
        
        if result and result.get("ok"):
            updates = result.get("result", [])
            if updates:
                # آپدیت آخرین offset
                self.offset = updates[-1]["update_id"] + 1
            return updates
        return []
    
    def send_message(self, chat_id: int, text: str, reply_to_message_id: int = None):
        """ارسال پیام ساده"""
        data = {
            "chat_id": chat_id,
            "text": text
        }
        if reply_to_message_id:
            data["reply_to_message_id"] = reply_to_message_id
        return self._post("sendMessage", data)
    
    def edit_message_text(self, chat_id: int, message_id: int, text: str):
        """ویرایش پیام"""
        data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text
        }
        return self._post("editMessageText", data)


def is_youtube_url(text: str) -> bool:
    patterns = [
        r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/',
        r'(https?://)?(www\.)?(m\.youtube\.com)/'
    ]
    return any(re.match(p, text) for p in patterns)


def get_audio_video_formats(url: str):
    """دریافت لیست فرمت‌های دارای صدا و تصویر"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            
            valid_formats = []
            seen = set()
            
            for f in formats:
                vcodec = f.get('vcodec', 'none')
                acodec = f.get('acodec', 'none')
                
                if vcodec != 'none' and acodec != 'none':
                    height = f.get('height', 0)
                    if height and height not in seen:
                        seen.add(height)
                        valid_formats.append({
                            'height': height,
                            'format_id': f['format_id'],
                            'ext': f.get('ext', 'mp4'),
                            'filesize': f.get('filesize', 0)
                        })
            
            valid_formats.sort(key=lambda x: x['height'], reverse=True)
            title = info.get('title', 'Unknown')
            
            return title, valid_formats
            
    except Exception as e:
        raise Exception(f"خطا در دریافت اطلاعات: {str(e)}")


def format_size(size_bytes):
    if not size_bytes:
        return "نامشخص"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024*1024):.1f} MB"
    else:
        return f"{size_bytes / (1024*1024*1024):.1f} GB"


def download_video(url: str, format_id: str) -> str:
    """دانلود ویدیو با فرمت مشخص"""
    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_PATH}/%(title)s.%(ext)s',
        'format': format_id,
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if os.path.exists(filename):
                return filename
            
            for ext in ['.mp4', '.mkv', '.webm']:
                test_path = filename.rsplit('.', 1)[0] + ext
                if os.path.exists(test_path):
                    return test_path
            
            return filename
    except Exception as e:
        raise Exception(f"دانلود ناموفق: {str(e)}")


# ========== بخش روبیکا ==========

def get_rubika_client():
    client = RubikaClient(name=RUBIKA_SESSION)
    client.start()
    return client


def send_to_rubika(file_path: str, caption: str = ""):
    """ارسال فایل به روبیکا"""
    client = None
    try:
        client = get_rubika_client()
        result = client.send_document(
            RUBIKA_TARGET,
            file_path,
            caption=caption or ""
        )
        return result
    finally:
        if client:
            try:
                client.disconnect()
            except Exception:
                pass


# ========== هندلرهای بله ==========

def handle_start(bot: BaleBot, chat_id: int):
    bot.send_message(
        chat_id,
        "🎬 ربات دانلودر یوتیوب\n\n"
        "لینک یوتیوب رو برام بفرست\n"
        "بعد از دانلود، خودکار به روبیکا ارسال میشه"
    )


def handle_cancel(bot: BaleBot, chat_id: int, user_id: int):
    if user_id in user_states and user_states[user_id].get('step') == 'downloading':
        user_states[user_id]['cancelled'] = True
        bot.send_message(chat_id, "❌ دانلود لغو شد")
    else:
        bot.send_message(chat_id, "هیچ دانلودی در جریان نیست")


def handle_message(bot: BaleBot, chat_id: int, user_id: int, text: str, message_id: int = None):
    
    # دستور لغو
    if text == "/cancel":
        handle_cancel(bot, chat_id, user_id)
        return
    
    # اگه کاربر توی حالت انتخاب کیفیت هست
    if user_id in user_states:
        state = user_states[user_id]
        
        if state['step'] == 'waiting_for_quality' and text.isdigit():
            choice = int(text)
            formats = state['formats']
            
            if 1 <= choice <= len(formats):
                selected = formats[choice - 1]
                
                # پیام شروع دانلود
                status_msg = bot.send_message(
                    chat_id,
                    f"⬇️ شروع دانلود...\n"
                    f"🎯 کیفیت: {selected['height']}p\n"
                    f"📦 حجم: {format_size(selected['filesize'])}\n\n"
                    f"بعد از دانلود، فایل به روبیکا ارسال میشه..."
                )
                
                status_msg_id = status_msg.get('result', {}).get('message_id') if status_msg else None
                
                user_states[user_id]['step'] = 'downloading'
                user_states[user_id]['status_msg_id'] = status_msg_id
                user_states[user_id]['cancelled'] = False
                
                try:
                    # دانلود ویدیو
                    filepath = download_video(state['url'], selected['format_id'])
                    
                    # چک کردن لغو شدن
                    if user_states.get(user_id, {}).get('cancelled'):
                        bot.send_message(chat_id, "❌ دانلود لغو شد")
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        del user_states[user_id]
                        return
                    
                    # آپدیت پیام
                    if status_msg_id:
                        bot.edit_message_text(
                            chat_id,
                            status_msg_id,
                            f"✅ دانلود کامل شد!\n"
                            f"📁 مسیر: {filepath}\n"
                            f"📊 حجم: {format_size(os.path.getsize(filepath))}\n\n"
                            f"🔼 در حال ارسال به روبیکا..."
                        )
                    
                    # ارسال به روبیکا
                    send_to_rubika(filepath, f"🎬 {state['title']}\nکیفیت: {selected['height']}p")
                    
                    if status_msg_id:
                        bot.edit_message_text(
                            chat_id,
                            status_msg_id,
                            f"✅ همه چیز انجام شد!\n\n"
                            f"🎬 {state['title'][:50]}...\n"
                            f"📊 کیفیت: {selected['height']}p\n"
                            f"📦 حجم: {format_size(os.path.getsize(filepath))}\n\n"
                            f"📨 فایل به روبیکا ارسال شد"
                        )
                    
                    # پاک کردن فایل از سرور بعد از ارسال
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    
                except Exception as e:
                    if status_msg_id:
                        bot.edit_message_text(chat_id, status_msg_id, f"❌ خطا: {str(e)}")
                    else:
                        bot.send_message(chat_id, f"❌ خطا: {str(e)}")
                
                finally:
                    if user_id in user_states:
                        del user_states[user_id]
                    
            else:
                bot.send_message(chat_id, f"❌ عدد بین 1 تا {len(formats)} رو وارد کن")
            return
        else:
            if state['step'] == 'waiting_for_quality':
                bot.send_message(chat_id, f"❌ لطفا یک عدد بین 1 تا {len(state['formats'])} وارد کن")
                return
    
    # بررسی لینک یوتیوب
    if not is_youtube_url(text):
        return
    
    # مرحله 1: دریافت اطلاعات ویدیو
    msg = bot.send_message(chat_id, "🔄 در حال دریافت اطلاعات ویدیو...")
    msg_id = msg.get('result', {}).get('message_id') if msg else None
    
    try:
        title, formats = get_audio_video_formats(text)
        
        if not formats:
            if msg_id:
                bot.edit_message_text(chat_id, msg_id, "❌ هیچ فرمت معتبری با صدا پیدا نشد")
            return
        
        # ساخت پیام لیست کیفیت‌ها
        message = f"🎬 {title[:50]}...\n\nلطفا شماره کیفیت مورد نظر رو وارد کن:\n\n"
        
        for i, fmt in enumerate(formats, 1):
            size_text = format_size(fmt['filesize'])
            message += f"{i}️⃣ {fmt['height']}p - {fmt['ext']} ({size_text})\n"
        
        message += "\nفقط عدد رو بفرست (مثال: 3)\n\nبرای لغو: /cancel"
        
        if msg_id:
            bot.edit_message_text(chat_id, msg_id, message)
        else:
            bot.send_message(chat_id, message)
        
        # ذخیره وضعیت کاربر
        user_states[user_id] = {
            'step': 'waiting_for_quality',
            'url': text,
            'formats': formats,
            'title': title
        }
        
    except Exception as e:
        if msg_id:
            bot.edit_message_text(chat_id, msg_id, f"❌ خطا: {str(e)}")
        else:
            bot.send_message(chat_id, f"❌ خطا: {str(e)}")


def main():
    bot = BaleBot(BALE_TOKEN)
    
    print("✅ ربات بله روشن شد...")
    print(f"📁 مسیر دانلود: {DOWNLOAD_PATH}")
    print(f"🔄 مقصد روبیکا: {RUBIKA_TARGET}")
    print(f"🔗 API Endpoint: {BALE_API_URL}")
    
    while True:
        try:
            updates = bot.get_updates()
            
            for update in updates:
                message = update.get("message")
                if not message:
                    continue
                
                chat_id = message.get("chat", {}).get("id")
                user_id = message.get("from", {}).get("id")
                text = message.get("text", "")
                message_id = message.get("message_id")
                
                if not chat_id:
                    continue
                
                # دستور start
                if text == "/start":
                    handle_start(bot, chat_id)
                else:
                    handle_message(bot, chat_id, user_id, text, message_id)
                    
        except Exception as e:
            print(f"خطا در حلقه اصلی: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
