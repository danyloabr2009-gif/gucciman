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
from telethon import TelegramClient, events, types, functions
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

# Bots to preload (warm up connection) - anonimgifterbot first for speed
PRELOAD_BOTS_STR = os.getenv("PRELOAD_BOTS", "anonimgifterbot,wallet,CryptoBot,send,tonRocketBot,xJetSwapBot")
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
    code_lower = code.lower()
    
    # Check giveaways first
    for prefix in GIVEAWAY_CODE_PREFIXES:
        if code_lower.startswith(prefix):
            code_type = f"розыгрыш ({prefix.rstrip('_')})"
            break
    else:
        # Then check gifts
        for prefix in GIFT_CODE_PREFIXES:
            if code_lower.startswith(prefix):
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
    logger.info(f"🔄 Предзагрузка ботов для ускорения...")
    
    start_time = time.time()
    success_count = 0
    
    for i, bot in enumerate(PRELOAD_BOTS, 1):
        logger.info(f"   [{i}/{len(PRELOAD_BOTS)}] Проверяю @{bot}...")
        try:
            entity = await client.get_entity(bot)
            stats.preloaded_bots += 1
            success_count += 1
            bot_name = getattr(entity, 'first_name', 'No name')
            logger.info(f"      ✅ @{bot} | {bot_name} (ID: {entity.id})")
        except Exception as e:
            logger.warning(f"      ⚠️ @{bot} не найден: {e}")
        await asyncio.sleep(0.2)  # Avoid flood
    
    elapsed = int((time.time() - start_time) * 1000)
    logger.info(f"🔄 Предзагрузка завершена за {elapsed}ms: {success_count}/{len(PRELOAD_BOTS)} ботов готовы")

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
    'chk_',      # anonimgifterbot checks (BUTTON PRESS)
    'c_',        # CryptoBot checks (/start command)
    'ck_',       # CryptoBot alternative (/start command)
    't6_',       # Wallet TON checks (/start command)
    'gift_',     # Generic gift prefix (/start command)
    'ton_',      # TON gifts (/start command)
    'start_',    # Some bots use this (/start command)
    'g_',        # Short gift prefix (/start command)
]

# Bots that need BUTTON PRESS instead of /start command
BUTTON_PRESS_BOTS = [
    'anonimgifterbot'     # ONLY @anonimgifterbot for checks
]

# Gift code prefixes that should use BUTTON PRESS instead of /start
BUTTON_PRESS_CODES = [
    'chk_',      # anonimgifterbot checks ONLY
]

# Keywords for gift/check buttons ONLY (no giveaways)
GIFT_BUTTONS = [
    'активировать', 'получить', 'забрать', 'claim', 'get', 
    'view', 'open', 'открыть', 'чек', 'gift', 'подарок',
    'receive', 'collect', 'activate', 'проверить', 'check',
    'activate check', 'активировать чек',  # Русские и английские кнопки
    'claim', 'activate', 'участвую', 'участвую!'  # Дополнительные кнопки
]

# Keywords for subscription requirements
SUBSCRIPTION_KEYWORDS = [
    'подпишись', 'подписка', 'subscribe', 'подпишитесь',
    'подписывайтесь', 'following', 'follow', 'тгк', 'канал',
    'условия:', 'условия', 'requirements', 'must follow',
    'обязательно', 'required', 'нужно подписаться'
]

# Keywords for reaction requirements
REACTION_KEYWORDS = [
    'реакция', 'поставь реакцию', 'reaction', 'лайк',
    'поставьте реакцию', 'поставь лайк', 'поставьте лайк',
    'react', 'like', 'heart', '❤️'
]

# Keywords for "Run/Start" buttons in popups
RUN_BUTTONS = [
    'запустить', 'запуск', 'run', 'start', 'открыть',
    'play', 'launch', 'начать', 'continue'
]

# NO MORE GIVEAWAYS - only gifts/checks

# Prefixes to IGNORE (not gifts, not giveaways)
IGNORE_CODE_PREFIXES = [
    'mup_',      # grouphelpbot - channel subscribe
    'ref_',      # referral links
    'sub_',      # subscription links
    'invite_',   # invite links
    'promo_',    # promo codes (not money)
]

# Giveaway/lottery bots to AUTO-JOIN
GIVEAWAY_BOTS = [
    'random1zebot',      # Lottery bot
    'bestrandom_bot',    # Lottery/giveaway bot  
    'randomizebot',      # Another lottery bot
]

# URL patterns for giveaways to AUTO-JOIN
GIVEAWAY_URL_PATTERNS = [
    '/joinlot',          # Random1zeBot lottery
    '/giveaway',         # Giveaway mini apps
    '/lottery',          # Lottery mini apps
    '/raffle',           # Raffle mini apps
]

BLACKLIST = [
    'разб', 'unban', 'report', 'жал', 'rule', 'правил', 
    'verify', 'kick', 'ban', 'mute', 'admin', 'отмен',
    'подписаться', 'subscribe', 'join', 'канал', 'channel',
    'разблокировать', 'заблокировать', 'блокировать', 'unlock',
    'забан', 'разбан', 'block', 'unblock', 'заблок', 'разблок'
]

WHITELIST = [
    'активировать', 'получить', 'забрать', 'claim', 'get', 
    'view', 'open', 'открыть', 'чек', 'gift', 'подарок',
    'receive', 'collect', 'activate'
]

def is_gift_code(code: str) -> tuple[bool, str]:
    """Check if code looks like a real gift. Returns (is_gift, reason)."""
    code_lower = code.lower()
    
    # Check IGNORE prefixes first
    for prefix in IGNORE_CODE_PREFIXES:
        if code_lower.startswith(prefix):
            return False, f"игнорируемый префикс '{prefix}'"
    
    # Check GIFT prefixes
    for prefix in GIFT_CODE_PREFIXES:
        if code_lower.startswith(prefix):
            return True, f"подарок '{prefix}'"
    
    # NO MORE GIVEAWAYS - only gifts/checks
    
    return False, "неизвестный формат"

async def smart_claim(client, event):
    """Detect and claim gifts from message buttons."""
    message = event.message
    claim_start = time.time()
    
    if not message.buttons:
        return False
    
    stats.messages_with_buttons += 1
    button_count = sum(len(row) for row in message.buttons)
    logger.info(f"🔘 Сообщение с кнопками! Найдено кнопок: {button_count}")
    
    # Check if message has gift/check buttons - INSTANT DETECTION
    has_gift_buttons = False
    gift_button_text = ""
    for row in message.buttons:
        for btn in row:
            btn_text = (btn.text or "").lower()
            if any(word in btn_text for word in GIFT_BUTTONS):
                has_gift_buttons = True
                gift_button_text = btn.text
                break
        if has_gift_buttons:
            break
    
    if has_gift_buttons:
        logger.info(f"🎁 🚨 НАЙДЕН ЧЕК! Кнопка: '{gift_button_text}' - МОМЕНТАЛЬНО НАЖИМАЮ...")

    for row_idx, row in enumerate(message.buttons):
        for btn_idx, btn in enumerate(row):
            btn_text = (btn.text or "").lower()
            btn_display = btn.text or "[Без текста]"
            
            # Log each button
            btn_type = "URL" if btn.url else ("CALLBACK" if btn.data else "OTHER")
            logger.debug(f"   [{row_idx}:{btn_idx}] {btn_type}: '{btn_display}'")
            
            # Check for gift/check buttons
            is_gift_button = any(word in btn_text for word in GIFT_BUTTONS)
            if is_gift_button:
                logger.info(f"� Найдена кнопка подарка/чека: '{btn_display}'")
                stats.gifts_detected += 1
            
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
                is_giveaway = False

                # Check if this is a giveaway/lottery URL - we want to JOIN these!
                for pattern in GIVEAWAY_URL_PATTERNS:
                    if pattern in url:
                        logger.info(f"🎰 РОЗЫГРЫШ: паттерн '{pattern}' — участвуем!")
                        is_giveaway = True
                        break

                # Check if URL is from giveaway bot
                if not is_giveaway:
                    for bot in GIVEAWAY_BOTS:
                        if f"t.me/{bot}" in url or f"/{bot}/" in url:
                            logger.info(f"🎰 РОЗЫГРЫШ: бот @{bot} — участвуем!")
                            is_giveaway = True
                            break

                # Extract start parameter (gift code) for other bots
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
                    
                    # Check if this code should use button press
                    code_lower = start_param.lower()
                    needs_button_press = any(code_lower.startswith(prefix) for prefix in BUTTON_PRESS_CODES)
                    
                    if needs_button_press:
                        logger.info(f"🎁 Найден подарок ({reason}) - нажимаю кнопку")
                        stats.gifts_detected += 1
                        
                        # Press the button directly
                        logger.info(f"🎯 Нажимаю кнопку 'Активировать чек'")
                        try:
                            await client(GetBotCallbackAnswerRequest(
                                peer=event.chat_id,
                                msg_id=message.id,
                                data=btn.data if btn.data else None
                            ))
                            elapsed = int((time.time() - claim_start) * 1000)
                            logger.info(f"✅ УСПЕХ! Подарок активирован за {elapsed}ms")
                            stats.gifts_claimed += 1
                            stats.last_gift_time = datetime.now()
                            asyncio.create_task(notify_gift(target_bot, start_param, elapsed, True))
                            return True
                        except Exception as e:
                            logger.error(f"❌ ОШИБКА активации подарка: {e}")
                            stats.gifts_failed += 1
                            asyncio.create_task(notify_gift(target_bot, start_param, 0, False))
                            return True
                    
                    # Process as gift/check
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
                    
                    # Check if target_bot is actually a bot (not a channel)
                    # Common giveaway channels to avoid
                    giveaway_channels = ['giveaway', 'gifts', 'crypto', 'ton', 'prize', 'lottery']
                    is_channel = any(channel in target_bot.lower() for channel in giveaway_channels) if target_bot else False
                    
                    # Fallback to default bot if text matches and not a channel
                    if not target_bot and is_gift_text:
                        target_bot = DEFAULT_GIFT_BOT
                        logger.debug(f"   Бот не найден в URL, использую дефолт: @{target_bot}")

                    # For ALL gifts/checks - just press the button (no /start commands)
                    logger.info(f"🎯 Нажимаю кнопку для {reason}")
                    try:
                        await client(GetBotCallbackAnswerRequest(
                            peer=event.chat_id,
                            msg_id=message.id,
                            data=btn.data if btn.data else None
                        ))
                        elapsed = int((time.time() - claim_start) * 1000)
                        logger.info(f"✅ УСПЕХ! Кнопка нажата за {elapsed}ms")
                        stats.gifts_claimed += 1
                        stats.last_gift_time = datetime.now()
                        asyncio.create_task(notify_gift(target_bot or "unknown", start_param, elapsed, True))
                        return True
                    except Exception as e:
                        logger.error(f"❌ ОШИБКА нажатия кнопки: {e}")
                        stats.gifts_failed += 1
                        asyncio.create_task(notify_gift(target_bot or "unknown", start_param, 0, False))
                        return True
    
    return False

async def extract_channels_from_text(text: str) -> list:
    """Extract Telegram channel usernames from text."""
    import re
    # Find @username patterns
    channels = re.findall(r'@([a-zA-Z0-9_]{5,})', text)
    return list(set(channels))  # Remove duplicates

async def process_giveaway_with_conditions(client, event, message):
    """Process giveaway with auto-detected conditions."""
    claim_start = time.time()
    try:
        message_text = message.text or ""
        conditions_met = []
        
        # PRIORITY 1: Click ALL subscription buttons FIRST (hyper fast)
        subscription_buttons = []
        for row_idx, row in enumerate(message.buttons):
            for btn_idx, btn in enumerate(row):
                btn_text = (btn.text or "").lower()
                if any(word in btn_text for word in ['подписаться', 'подписка', 'subscribe']):
                    subscription_buttons.append((row_idx, btn_idx, btn))
        
        if subscription_buttons:
            logger.info(f"🚀 ГИПЕР-СКОРОСТЬ: Найдено {len(subscription_buttons)} кнопок подписки")
            for i, (row_idx, btn_idx, btn) in enumerate(subscription_buttons, 1):
                logger.info(f"   [{i}/{len(subscription_buttons)}] Нажимаю 'Подписаться'...")
                click_start = time.time()
                try:
                    await client(GetBotCallbackAnswerRequest(
                        peer=event.chat_id,
                        msg_id=message.id,
                        data=btn.data if btn.data else None
                    ))
                    click_elapsed = int((time.time() - click_start) * 1000)
                    logger.info(f"      ✅ Подписаться нажата за {click_elapsed}ms")
                    conditions_met.append("подписка")
                    await asyncio.sleep(0.05)  # Minimal delay for speed
                except Exception as e:
                    logger.warning(f"      ⚠️ Ошибка: {e}")
        
        # PRIORITY 2: Click "Я подписался" buttons
        subscribed_buttons = []
        for row_idx, row in enumerate(message.buttons):
            for btn_idx, btn in enumerate(row):
                btn_text = (btn.text or "").lower()
                if any(word in btn_text for word in ['я подписался', 'подписался', 'subscribed']):
                    subscribed_buttons.append((row_idx, btn_idx, btn))
        
        if subscribed_buttons:
            logger.info(f"🎯 ПОДТВЕРЖДЕНИЕ: Найдено {len(subscribed_buttons)} кнопок 'Я подписался'")
            for i, (row_idx, btn_idx, btn) in enumerate(subscribed_buttons, 1):
                logger.info(f"   [{i}/{len(subscribed_buttons)}] Нажимаю 'Я подписался'...")
                click_start = time.time()
                try:
                    await client(GetBotCallbackAnswerRequest(
                        peer=event.chat_id,
                        msg_id=message.id,
                        data=btn.data if btn.data else None
                    ))
                    click_elapsed = int((time.time() - click_start) * 1000)
                    logger.info(f"      ✅ Я подписался нажата за {click_elapsed}ms")
                    conditions_met.append("подтверждение")
                    await asyncio.sleep(0.05)  # Minimal delay for speed
                except Exception as e:
                    logger.warning(f"      ⚠️ Ошибка: {e}")
        
        # PRIORITY 3: Auto-subscribe to mentioned channels
        channels = await extract_channels_from_text(message_text)
        if channels:
            logger.info(f"� АВТО-ПОДПИСКА: Найдены каналы: {channels}")
            for i, channel in enumerate(channels, 1):
                logger.info(f"   [{i}/{len(channels)}] Подписка на @{channel}...")
                try:
                    await client(functions.channels.JoinChannelRequest(
                        channel=channel
                    ))
                    logger.info(f"      ✅ Подписка на @{channel} успешна")
                    conditions_met.append(f"канал @{channel}")
                    await asyncio.sleep(0.1)  # Fast channel subscription
                except Exception as e:
                    logger.warning(f"      ⚠️ Ошибка подписки на @{channel}: {e}")
        
        # PRIORITY 4: Click participation buttons
        participation_buttons = []
        for row_idx, row in enumerate(message.buttons):
            for btn_idx, btn in enumerate(row):
                btn_text = (btn.text or "").lower()
                if any(word in btn_text for word in ['участвовать', 'участие', 'join', 'take part', 'учавствовать', 'принять участие', 'enter', 'participate', 'register']):
                    participation_buttons.append((row_idx, btn_idx, btn))
        
        if participation_buttons:
            logger.info(f"🎰 УЧАСТИЕ: Найдено {len(participation_buttons)} кнопок участия")
            for i, (row_idx, btn_idx, btn) in enumerate(participation_buttons, 1):
                logger.info(f"   [{i}/{len(participation_buttons)}] Нажимаю '{btn.text}'...")
                click_start = time.time()
                try:
                    result = await client(GetBotCallbackAnswerRequest(
                        peer=event.chat_id,
                        msg_id=message.id,
                        data=btn.data if btn.data else None
                    ))
                    click_elapsed = int((time.time() - click_start) * 1000)
                    logger.info(f"      ✅ {btn.text} нажата за {click_elapsed}ms")
                    conditions_met.append("участие")
                    
                    # Handle popup if appeared
                    if hasattr(result, 'message') and result.message:
                        logger.info(f"      📱 Ответ: {result.message[:40]}...")
                        await asyncio.sleep(0.05)
                    
                    await asyncio.sleep(0.05)
                except Exception as e:
                    logger.warning(f"      ⚠️ Ошибка: {e}")
        
        # PRIORITY 5: Add reaction if requested
        has_reaction_req = any(word in message_text for word in REACTION_KEYWORDS)
        if has_reaction_req:
            logger.info(f"❤️ РЕАКЦИЯ: Ставлю реакцию...")
            try:
                reaction_start = time.time()
                await client(functions.messages.SendReactionRequest(
                    peer=event.chat_id,
                    msg_id=message.id,
                    reaction=[types.ReactionEmoji(emoticon="❤️")]
                ))
                reaction_elapsed = int((time.time() - reaction_start) * 1000)
                logger.info(f"      ✅ Реакция ❤️ поставлена за {reaction_elapsed}ms")
                conditions_met.append("реакция")
            except Exception as e:
                logger.warning(f"      ⚠️ Ошибка реакции: {e}")
        
        elapsed = int((time.time() - claim_start) * 1000)
        logger.info(f"🚀 ГИПЕР-СКОРОСТЬ! Выполнено: {', '.join(conditions_met)} за {elapsed}ms")
        stats.gifts_claimed += 1
        stats.last_gift_time = datetime.now()
        asyncio.create_task(notify_gift("hyper", f"действий: {len(conditions_met)}", elapsed, True))
        return True
        
    except Exception as e:
        logger.error(f"❌ ОШИБКА гипер-обработки: {e}")
        stats.gifts_failed += 1
        asyncio.create_task(notify_gift("hyper", "ошибка", 0, False))
        return False

async def process_giveaway_participation(client, event, btn, message):
    """Process simple giveaway participation."""
    claim_start = time.time()
    try:
        # Add reaction first
        try:
            await client(functions.messages.SendReactionRequest(
                peer=event.chat_id,
                msg_id=message.id,
                reaction=[types.ReactionEmoji(emoticon="❤️")]
            ))
            logger.info(f"   ❤️ Поставил реакцию")
        except Exception as e:
            logger.warning(f"   ⚠️ Не удалось поставить реакцию: {e}")
        
        # Click participation button
        logger.info(f"🎯 Нажимаю кнопку: '{btn.text}'")
        await client(GetBotCallbackAnswerRequest(
            peer=event.chat_id,
            msg_id=message.id,
            data=btn.data if btn.data else None
        ))
        
        elapsed = int((time.time() - claim_start) * 1000)
        logger.info(f"✅ УСПЕХ! Участие подтверждено за {elapsed}ms")
        stats.gifts_claimed += 1
        stats.last_gift_time = datetime.now()
        asyncio.create_task(notify_gift("giveaway", btn.text or "участие", elapsed, True))
        return True
        
    except Exception as e:
        logger.error(f"❌ ОШИБКА участия: {e}")
        stats.gifts_failed += 1
        asyncio.create_task(notify_gift("giveaway", btn.text or "участие", 0, False))
        return False

# ============================================================================
# MESSAGE HANDLER (PARALLEL PROCESSING)
# ============================================================================
async def process_message(client, event):
    """Process a single message (runs in parallel)."""
    stats.messages_total += 1
    stats.last_message_time = datetime.now()
    receive_time = time.time()
    
    # Get chat info (minimal for speed)
    try:
        chat = await client.get_entity(event.chat_id)
        chat_name = getattr(chat, 'title', getattr(chat, 'first_name', f"ID:{event.chat_id}"))
    except Exception:
        chat_name = f"ID:{event.chat_id}"
    
    # MONITORING: Show every message check with status
    message_text = (event.message.text or "")[:50]
    logger.info(f"👁️ МОНИТОРИНГ: {chat_name} | #{event.message.id} | '{message_text}...'")
    
    # Process the message for gifts IMMEDIATELY
    try:
        claimed = await smart_claim(client, event)
        elapsed = int((time.time() - receive_time) * 1000)
        
        if claimed:
            logger.info(f"🎯 ✅ ЧЕК ПОЙМАН за {elapsed}ms | {chat_name}")
        else:
            logger.info(f"📝 ⏭️ Не чек ({elapsed}ms) | {chat_name}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    
    # Log stats less frequently (every 50 messages)
    if stats.messages_total % 50 == 0:
        await log_stats(client)

def setup_handlers(client):
    """Setup message event handlers with parallel processing."""
    
    @client.on(events.NewMessage(chats=TARGET_CHANNELS))
    async def handler(event):
        # Process in parallel - don't block other messages
        asyncio.create_task(process_message(client, event))

def log_stats():
    """Log current statistics."""
    logger.info("=" * 60)
    logger.info(f"📊 СТАТИСТИКА | Uptime: {stats.uptime()}")
    logger.info(f"   📨 Сообщений: {stats.messages_total} | С кнопками: {stats.messages_with_buttons}")
    logger.info(f"   🎁 Подарков: {stats.gifts_detected} | Пропущено: {stats.codes_skipped}")
    logger.info(f"   [OK] Успешно: {stats.gifts_claimed} | [ERR] Ошибок: {stats.gifts_failed}")
    
    if stats.gifts_detected > 0:
        success_rate = (stats.gifts_claimed / stats.gifts_detected) * 100
        logger.info(f"   📈 Успешность: {success_rate:.1f}%")
    
    if stats.messages_total > 0:
        button_rate = (stats.messages_with_buttons / stats.messages_total) * 100
        logger.info(f"   🔘 С кнопками: {button_rate:.1f}% сообщений")
    
    if stats.last_gift_time:
        time_ago = int((datetime.now() - stats.last_gift_time).total_seconds())
        if time_ago < 60:
            time_str = f"{time_ago}s назад"
        elif time_ago < 3600:
            time_str = f"{time_ago//60}m назад"
        else:
            time_str = f"{time_ago//3600}h назад"
        logger.info(f"   ⏰ Последний подарок: {time_str}")
    
    if stats.restarts > 0:
        logger.info(f"   [RESTART] Перезапусков: {stats.restarts}")
    
    logger.info("=" * 60)

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
        logger.info("🚀 МОНИТОРИНГ @anonimgifterbot ЗАПУЩЕН!")
        logger.info("   👁️ Статус: АКТИВЕН")
        logger.info("   ⚡ Режим: МОМЕНТАЛЬНОЕ НАЖАТИЕ")
        logger.info("   🎯 Фокус: Чеки с кнопками 'Активировать чек'")
        logger.info("   📊 Каналов: {} | Ботов: 1".format(len(TARGET_CHANNELS)))
        logger.info("   📬 Уведомления: Saved Messages")
        logger.info("")
        
        # Send startup notification
        channels_list = "\n".join([f"• {ch}" for ch in TARGET_CHANNELS[:5]])
        if len(TARGET_CHANNELS) > 5:
            channels_list += f"\n... и еще {len(TARGET_CHANNELS)-5}"
        
        bots_list = "\n".join([f"• @{bot}" for bot in PRELOAD_BOTS[:5]])
        if len(PRELOAD_BOTS) > 5:
            bots_list += f"\n... и еще {len(PRELOAD_BOTS)-5}"
        
        await notify(f"""🚀 **Gift Claimer запущен!**

📡 **Каналы ({len(TARGET_CHANNELS)}):**
{channels_list}

🤖 **Боты для предзагрузки ({len(PRELOAD_BOTS)}):**
{bots_list}

✅ Загружено: {stats.preloaded_bots}/{len(PRELOAD_BOTS)}""", silent=True)
        
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
    logger.info(f"🤖 PRELOAD BOTS ({len(PRELOAD_BOTS)}):")
    for i, bot in enumerate(PRELOAD_BOTS, 1):
        logger.info(f"   {i}. @{bot}")
    logger.info(f"🔍 WHITELIST: {', '.join(WHITELIST[:5])}...")
    logger.info(f"⛔ BLACKLIST: {', '.join(BLACKLIST[:5])}...")
    logger.info("=" * 50)
    
    # Auto-restart loop
    while stats.restarts < MAX_RETRIES:
        should_restart = await run_client()
        
        if not should_restart:
            break
        
        stats.restarts += 1
        logger.warning(f"[RESTART] Перезапуск {stats.restarts}/{MAX_RETRIES} через {RETRY_DELAY}s...")
        await asyncio.sleep(RETRY_DELAY)
    
    if stats.restarts >= MAX_RETRIES:
        logger.error(f"[ERROR] Превышено максимальное число перезапусков ({MAX_RETRIES})")
    
    logger.info("[BYE] Goodbye!")

if __name__ == "__main__":
    asyncio.run(main())
