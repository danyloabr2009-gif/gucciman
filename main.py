#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Gift Claimer v10.0
Автоматический перехват подарков/чеков в Telegram каналах.
Features: Предзагрузка ботов, параллельная обработка, авто-рестарт, уведомления
"""

import asyncio
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from telethon.errors import SessionPasswordNeededError, FloodWaitError

# Load environment variables
load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME", "gift_claimer_session")
STRING_SESSION = os.getenv("STRING_SESSION", "")
DEFAULT_GIFT_BOT = os.getenv("DEFAULT_GIFT_BOT", "anonimgifterbot")
NOTIFY_USER = os.getenv("NOTIFY_USER", "me")  # "me" = Saved Messages

# Parse target channels from env
channels_str = os.getenv("TARGET_CHANNELS", "")
TARGET_CHANNELS = []
if channels_str:
    for ch in channels_str.split(","):
        ch = ch.strip()
        if ch:
            try:
                TARGET_CHANNELS.append(int(ch))
            except ValueError:
                TARGET_CHANNELS.append(ch)

# Bots to preload (warm up connection)
PRELOAD_BOTS_STR = os.getenv("PRELOAD_BOTS", "wallet,CryptoBot,send,tonRocketBot,xJetSwapBot")
PRELOAD_BOTS = [b.strip() for b in PRELOAD_BOTS_STR.split(",") if b.strip()]

# Auto-restart settings
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "10"))

# ============================================================================
# LOGGING SETUP
# ============================================================================
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ============================================================================
# STATISTICS
# ============================================================================
class Stats:
    def __init__(self):
        self.start_time = None
        self.messages_total = 0
        self.messages_with_buttons = 0
        self.gifts_detected = 0
        self.gifts_claimed = 0
        self.gifts_failed = 0
        self.last_message_time = None
        self.last_gift_time = None
        self.restarts = 0
        self.preloaded_bots = 0
        self.codes_skipped = 0  # Codes filtered out
    
    def uptime(self):
        if not self.start_time:
            return "0s"
        delta = int(time.time() - self.start_time)
        hours, remainder = divmod(delta, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m"
        elif minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

stats = Stats()

# Global client reference for notifications
_client: Optional[TelegramClient] = None

# ============================================================================
# NOTIFICATIONS
# ============================================================================
async def notify(message: str, silent: bool = False):
    """Send notification to user (Saved Messages by default)."""
    if not _client:
        return
    try:
        await _client.send_message(NOTIFY_USER, message, silent=silent)
        logger.debug(f"📤 Уведомление отправлено: {message[:50]}...")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось отправить уведомление: {e}")

async def notify_gift(bot: str, code: str, elapsed_ms: int, success: bool):
    """Send gift notification."""
    status = "✅ УСПЕХ" if success else "❌ ОШИБКА"
    
    # Determine code type
    code_type = "неизвестный"
    for prefix in GIFT_CODE_PREFIXES:
        if code.lower().startswith(prefix):
            code_type = prefix.rstrip('_')
            break
    
    msg = f"""🎁 **ПОДАРОК {status}**

🤖 Бот: @{bot}
🔑 Код: `{code}`
📋 Тип: {code_type}
⏱ Время: {elapsed_ms}ms

📊 Статистика:
   Поймано: {stats.gifts_claimed}
   Пропущено: {stats.codes_skipped}

⏰ {datetime.now().strftime('%H:%M:%S')}"""
    await notify(msg)

# ============================================================================
# BOT PRELOADING
# ============================================================================
async def preload_bots(client: TelegramClient):
    """Preload bots to warm up connections for faster claiming."""
    logger.info(f"🔄 Предзагрузка ботов ({len(PRELOAD_BOTS)})...")
    
    for bot in PRELOAD_BOTS:
        try:
            entity = await client.get_entity(bot)
            stats.preloaded_bots += 1
            logger.info(f"   ✅ @{bot} загружен (ID: {entity.id})")
        except Exception as e:
            logger.warning(f"   ⚠️ @{bot} не найден: {e}")
        await asyncio.sleep(0.3)  # Avoid flood
    
    logger.info(f"🔄 Предзагрузка завершена: {stats.preloaded_bots}/{len(PRELOAD_BOTS)}")

# ============================================================================
# VALIDATION
# ============================================================================
def validate_config():
    """Validate required configuration."""
    errors = []
    if not API_ID:
        errors.append("API_ID not set")
    if not API_HASH:
        errors.append("API_HASH not set")
    if not TARGET_CHANNELS:
        errors.append("TARGET_CHANNELS not set")
    
    if errors:
        for err in errors:
            logger.error(f"Config error: {err}")
        logger.error("Please check your .env file or environment variables")
        sys.exit(1)

# ============================================================================
# CLIENT SETUP
# ============================================================================
def create_client():
    """Create Telegram client with appropriate session."""
    if STRING_SESSION:
        logger.info("Using StringSession for authentication")
        return TelegramClient(StringSession(STRING_SESSION), int(API_ID), API_HASH)
    else:
        logger.info(f"Using file session: {SESSION_NAME}")
        return TelegramClient(SESSION_NAME, int(API_ID), API_HASH)

# ============================================================================
# GIFT CLAIMING LOGIC
# ============================================================================

# Prefixes of REAL gift/check codes (case-insensitive)
GIFT_CODE_PREFIXES = [
    'chk_',      # anonimgifterbot checks
    'c_',        # CryptoBot checks  
    'ck_',       # CryptoBot alternative
    't6_',       # Wallet TON checks
    'gift_',     # Generic gift prefix
    'ton_',      # TON gifts
    'start_',    # Some bots use this
    'g_',        # Short gift prefix
]

# Prefixes to IGNORE (not gifts)
IGNORE_CODE_PREFIXES = [
    'mup_',      # grouphelpbot - channel subscribe
    'lot_',      # bestrandom_bot - lottery
    'ref_',      # referral links
    'sub_',      # subscription links
    'join_',     # join group/channel
    'invite_',   # invite links
    'promo_',    # promo codes (not money)
    'bonus_',    # bonus (usually not money)
]

BLACKLIST = [
    'разб', 'unban', 'report', 'жал', 'rule', 'правил', 
    'verify', 'kick', 'ban', 'mute', 'admin', 'отмен',
    'подписаться', 'subscribe', 'join', 'канал', 'channel'
]

WHITELIST = [
    'активировать', 'получить', 'забрать', 'claim', 'get', 
    'view', 'open', 'открыть', 'чек', 'gift', 'подарок',
    'receive', 'collect', 'activate'
]

def is_gift_code(code: str) -> tuple[bool, str]:
    """Check if code looks like a real gift. Returns (is_gift, reason)."""
    code_lower = code.lower()
    
    # First check if it's in ignore list
    for prefix in IGNORE_CODE_PREFIXES:
        if code_lower.startswith(prefix):
            return False, f"игнор-префикс '{prefix}'"
    
    # Then check if it's a known gift prefix
    for prefix in GIFT_CODE_PREFIXES:
        if code_lower.startswith(prefix):
            return True, f"подарок '{prefix}'"
    
    # Unknown prefix - still try (might be new format)
    return True, "неизвестный формат (пробуем)"

async def smart_claim(client, event):
    """Detect and claim gifts from message buttons."""
    message = event.message
    claim_start = time.time()
    
    if not message.buttons:
        return False
    
    stats.messages_with_buttons += 1
    button_count = sum(len(row) for row in message.buttons)
    logger.info(f"🔘 Сообщение с кнопками! Найдено кнопок: {button_count}")

    for row_idx, row in enumerate(message.buttons):
        for btn_idx, btn in enumerate(row):
            btn_text = (btn.text or "").lower()
            btn_display = btn.text or "[Без текста]"
            
            # Log each button
            btn_type = "URL" if btn.url else ("CALLBACK" if btn.data else "OTHER")
            logger.debug(f"   [{row_idx}:{btn_idx}] {btn_type}: '{btn_display}'")
            
            # Blacklist check
            matched_blacklist = [w for w in BLACKLIST if w in btn_text]
            if matched_blacklist:
                logger.debug(f"   ⛔ Пропуск (blacklist: {matched_blacklist})")
                continue

            # Whitelist check
            matched_whitelist = [w for w in WHITELIST if w in btn_text]
            is_gift_text = len(matched_whitelist) > 0
            
            if is_gift_text:
                logger.info(f"   ✨ СОВПАДЕНИЕ! Триггеры: {matched_whitelist}")
                stats.gifts_detected += 1

            # Option 1: Callback button (no URL)
            if btn.data and (is_gift_text or not btn_text):
                logger.info(f"🎯 CALLBACK кнопка: '{btn_display}'")
                try:
                    await client(GetBotCallbackAnswerRequest(
                        peer=event.chat_id,
                        msg_id=message.id,
                        data=btn.data
                    ))
                    elapsed = int((time.time() - claim_start) * 1000)
                    logger.info(f"✅ УСПЕХ! Callback нажат за {elapsed}ms")
                    stats.gifts_claimed += 1
                    stats.last_gift_time = datetime.now()
                    asyncio.create_task(notify_gift("callback", btn_display, elapsed, True))
                    return True
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка callback (попытка засчитана): {e}")
                    stats.gifts_failed += 1
                    asyncio.create_task(notify_gift("callback", btn_display, 0, False))
                    return True

            # Option 2: URL button (Activate check)
            if btn.url:
                url = btn.url.lower()
                original_url = btn.url
                start_param = None
                target_bot = None

                # Extract start parameter (gift code)
                if "start=" in url:
                    start_param = url.split("start=")[1].split("&")[0]
                elif "startapp=" in url:
                    start_param = url.split("startapp=")[1].split("&")[0]
                
                if start_param:
                    # Check if this is a real gift code
                    is_gift, reason = is_gift_code(start_param)
                    
                    if not is_gift:
                        logger.info(f"⏭️ ПРОПУСК: код '{start_param[:25]}' — {reason}")
                        stats.codes_skipped += 1
                        continue
                    
                    logger.info(f"🔗 URL кнопка с кодом: {start_param}")
                    logger.info(f"   📋 Анализ: {reason}")
                    stats.gifts_detected += 1
                    
                    # Try to extract bot username from URL
                    if "t.me/" in url:
                        try:
                            target_bot = url.split("t.me/")[1].split("?")[0].replace("/", "")
                        except Exception:
                            pass
                    elif "tg://resolve" in url:
                        try:
                            target_bot = url.split("domain=")[1].split("&")[0]
                        except Exception:
                            pass
                    
                    # Fallback to default bot if text matches
                    if not target_bot and is_gift_text:
                        target_bot = DEFAULT_GIFT_BOT
                        logger.debug(f"   Бот не найден в URL, использую дефолт: @{target_bot}")

                    # Send /start command to bot
                    if target_bot:
                        logger.info(f"🎯 Отправляю /start @{target_bot}")
                        try:
                            await client.send_message(target_bot, f"/start {start_param}")
                            elapsed = int((time.time() - claim_start) * 1000)
                            logger.info(f"✅ УСПЕХ! /start отправлен за {elapsed}ms")
                            stats.gifts_claimed += 1
                            stats.last_gift_time = datetime.now()
                            # Send notification (don't await to not slow down)
                            asyncio.create_task(notify_gift(target_bot, start_param, elapsed, True))
                            return True
                        except FloodWaitError as e:
                            logger.error(f"🚫 FLOOD WAIT: {e.seconds}s")
                            stats.gifts_failed += 1
                            asyncio.create_task(notify_gift(target_bot, start_param, 0, False))
                            return True
                        except Exception as e:
                            logger.error(f"❌ ОШИБКА отправки /start: {e}")
                            stats.gifts_failed += 1
                            asyncio.create_task(notify_gift(target_bot, start_param, 0, False))
                            return True
                    else:
                        logger.debug(f"   URL без бота: {original_url[:50]}")
    
    return False

# ============================================================================
# MESSAGE HANDLER (PARALLEL PROCESSING)
# ============================================================================
async def process_message(client, event):
    """Process a single message (runs in parallel)."""
    stats.messages_total += 1
    stats.last_message_time = datetime.now()
    receive_time = time.time()
    
    # Get chat info
    chat_title = "Channel"
    try:
        chat = await event.get_chat()
        if hasattr(chat, 'title'):
            chat_title = chat.title[:20]
    except Exception:
        pass
    
    message = event.message
    has_buttons = bool(message.buttons)
    text_preview = (message.text or "")[:40].replace('\n', ' ')
    if not text_preview and message.media:
        text_preview = "[Медиа]"
    
    # Log incoming message
    btn_info = f" [🔘 {sum(len(r) for r in message.buttons)} кнопок]" if has_buttons else ""
    logger.info(f"📨 #{stats.messages_total} | {chat_title}{btn_info}")
    if text_preview:
        logger.debug(f"   Текст: {text_preview}...")
    
    # Try to claim
    was_gift = await smart_claim(client, event)
    
    if was_gift:
        elapsed = int((time.time() - receive_time) * 1000)
        logger.info(f"🎁 ПОДАРОК ОБРАБОТАН! Общее время: {elapsed}ms")
        log_stats()

def setup_handlers(client):
    """Setup message event handlers with parallel processing."""
    
    @client.on(events.NewMessage(chats=TARGET_CHANNELS))
    async def handler(event):
        # Process in parallel - don't block other messages
        asyncio.create_task(process_message(client, event))

def log_stats():
    """Log current statistics."""
    logger.info("=" * 50)
    logger.info(f"📊 СТАТИСТИКА | Uptime: {stats.uptime()}")
    logger.info(f"   📨 Сообщений: {stats.messages_total} | С кнопками: {stats.messages_with_buttons}")
    logger.info(f"   🎁 Подарков найдено: {stats.gifts_detected} | Пропущено: {stats.codes_skipped}")
    logger.info(f"   ✅ Успешно: {stats.gifts_claimed} | ❌ Ошибок: {stats.gifts_failed}")
    if stats.gifts_detected > 0:
        success_rate = (stats.gifts_claimed / stats.gifts_detected) * 100
        logger.info(f"   📈 Успешность: {success_rate:.1f}%")
    if stats.last_gift_time:
        logger.info(f"   ⏰ Последний подарок: {stats.last_gift_time.strftime('%H:%M:%S')}")
    logger.info("=" * 50)

# ============================================================================
# LOGIN SYSTEM
# ============================================================================
async def login_with_qr(client):
    """Login using QR code (for local development)."""
    try:
        import qrcode
    except ImportError:
        logger.error("qrcode package not installed. Run: pip install qrcode")
        return False
    
    logger.info("QR code login required. Scan with Telegram app.")
    
    qr_login = await client.qr_login()
    qr = qrcode.QRCode()
    qr.add_data(qr_login.url)
    qr.make()
    qr.print_ascii(invert=True)
    
    try:
        await qr_login.wait()
    except SessionPasswordNeededError:
        logger.warning("2FA password required!")
        pwd = input("Enter 2FA password: ")
        await client.sign_in(password=pwd)
        logger.info("Password accepted!")
    
    return True

async def login_system(client):
    """Handle authentication."""
    if await client.is_user_authorized():
        me = await client.get_me()
        logger.info(f"Logged in as: {me.first_name} (@{me.username})")
        return True

    # If using StringSession, it should already be authorized
    if STRING_SESSION:
        logger.error("StringSession provided but not authorized!")
        logger.error("Generate a new session with: python generate_session.py")
        return False
    
    # Try QR login for file session
    return await login_with_qr(client)

# ============================================================================
# MAIN WITH AUTO-RESTART
# ============================================================================
async def run_client():
    """Run the client once. Returns True if should restart."""
    global _client
    
    client = create_client()
    _client = client  # Set global for notifications
    setup_handlers(client)
    
    try:
        await client.connect()
        
        if not await login_system(client):
            logger.error("❌ Login failed!")
            return False  # Don't restart on auth failure
        
        # Preload bots for faster claiming
        await preload_bots(client)
        
        stats.start_time = time.time()
        logger.info("")
        logger.info("🚀 МОНИТОРИНГ ЗАПУЩЕН!")
        logger.info("   Ожидаю сообщения в каналах...")
        logger.info("   Уведомления: Saved Messages")
        logger.info("")
        
        # Send startup notification
        await notify(f"🚀 Gift Claimer запущен!\n📡 Каналов: {len(TARGET_CHANNELS)}\n🤖 Ботов загружено: {stats.preloaded_bots}", silent=True)
        
        await client.run_until_disconnected()
        return False  # Normal disconnect
        
    except KeyboardInterrupt:
        logger.info("🛑 Остановка по запросу...")
        return False
    except Exception as e:
        logger.error(f"💥 Ошибка: {e}")
        logger.error(traceback.format_exc())
        return True  # Should restart
    finally:
        log_stats()
        if client.is_connected():
            await client.disconnect()
        _client = None

async def main():
    """Main entry point with auto-restart."""
    print()
    logger.info("=" * 50)
    logger.info("🎁 Telegram Gift Claimer v10.0")
    logger.info("   Auto-restart | Parallel | Notifications")
    logger.info("=" * 50)
    
    validate_config()
    
    # Show configuration
    logger.info("📋 КОНФИГУРАЦИЯ:")
    logger.info(f"   API_ID: {API_ID}")
    logger.info(f"   API_HASH: {API_HASH[:8]}...{API_HASH[-4:]}")
    logger.info(f"   SESSION: {'StringSession' if STRING_SESSION else 'File'}")
    logger.info(f"   DEFAULT_BOT: @{DEFAULT_GIFT_BOT}")
    logger.info(f"   NOTIFY: {NOTIFY_USER}")
    logger.info(f"   MAX_RETRIES: {MAX_RETRIES}")
    logger.info("")
    logger.info(f"📡 КАНАЛЫ ({len(TARGET_CHANNELS)}):")
    for i, ch in enumerate(TARGET_CHANNELS, 1):
        logger.info(f"   {i}. {ch}")
    logger.info("")
    logger.info(f"🤖 PRELOAD BOTS: {', '.join(PRELOAD_BOTS[:5])}...")
    logger.info(f"🔍 WHITELIST: {', '.join(WHITELIST[:5])}...")
    logger.info(f"⛔ BLACKLIST: {', '.join(BLACKLIST[:5])}...")
    logger.info("=" * 50)
    
    # Auto-restart loop
    while stats.restarts < MAX_RETRIES:
        should_restart = await run_client()
        
        if not should_restart:
            break
        
        stats.restarts += 1
        logger.warning(f"🔄 Перезапуск {stats.restarts}/{MAX_RETRIES} через {RETRY_DELAY}s...")
        await asyncio.sleep(RETRY_DELAY)
    
    if stats.restarts >= MAX_RETRIES:
        logger.error(f"❌ Превышено максимальное число перезапусков ({MAX_RETRIES})")
    
    logger.info("👋 Goodbye!")

if __name__ == "__main__":
    asyncio.run(main())
