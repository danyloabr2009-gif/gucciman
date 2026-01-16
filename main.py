#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Gift Claimer v8.0
Автоматический перехват подарков/чеков в Telegram каналах.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from telethon.errors import SessionPasswordNeededError

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

# ============================================================================
# LOGGING SETUP
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

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
async def smart_claim(client, event):
    """Detect and claim gifts from message buttons."""
    message = event.message
    
    if not message.buttons:
        return False

    for row in message.buttons:
        for btn in row:
            btn_text = (btn.text or "").lower()
            
            # Blacklist - ignore these buttons
            blacklist = [
                'разб', 'unban', 'report', 'жал', 'rule', 'правил', 
                'verify', 'kick', 'ban', 'mute', 'admin', 'отмен',
                'подписаться', 'subscribe', 'join'
            ]
            if any(bad_word in btn_text for bad_word in blacklist):
                continue

            # Whitelist - trigger words for gift buttons
            whitelist = [
                'активировать', 'получить', 'забрать', 'claim', 'get', 
                'view', 'open', 'открыть', 'чек', 'gift', 'подарок'
            ]
            is_gift_text = any(good_word in btn_text for good_word in whitelist)

            # Option 1: Callback button (no URL)
            if btn.data and (is_gift_text or not btn_text):
                try:
                    await client(GetBotCallbackAnswerRequest(
                        peer=event.chat_id,
                        msg_id=message.id,
                        data=btn.data
                    ))
                    logger.info(f"[GIFT] Pressed callback button: {btn.text or '[No text]'}")
                    return True
                except Exception as e:
                    logger.debug(f"Callback button error (ignored): {e}")
                    return True

            # Option 2: URL button (Activate check)
            if btn.url:
                url = btn.url.lower()
                start_param = None
                target_bot = None

                # Extract start parameter (gift code)
                if "start=" in url:
                    start_param = url.split("start=")[1].split("&")[0]
                elif "startapp=" in url:
                    start_param = url.split("startapp=")[1].split("&")[0]
                
                if start_param:
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

                    # Send /start command to bot
                    if target_bot:
                        try:
                            logger.info(f"[GIFT] Activating via URL for @{target_bot}")
                            await client.send_message(target_bot, f"/start {start_param}")
                            logger.info(f"[GIFT] /start command sent!")
                            return True
                        except Exception as e:
                            logger.error(f"Error sending /start: {e}")
                            return True
    
    return False

# ============================================================================
# MESSAGE HANDLER
# ============================================================================
def setup_handlers(client):
    """Setup message event handlers."""
    
    @client.on(events.NewMessage(chats=TARGET_CHANNELS))
    async def handler(event):
        # First - try to claim
        was_gift = await smart_claim(client, event)

        # Then - log the message
        try:
            message = event.message
            
            chat_title = "Channel"
            sender_name = "User"
            try:
                chat = await event.get_chat()
                if hasattr(chat, 'title'):
                    chat_title = chat.title
                sender = await message.get_sender()
                if sender and hasattr(sender, 'first_name'):
                    sender_name = sender.first_name
            except Exception:
                pass

            text = (message.text or "").replace('\n', ' ')
            
            if was_gift:
                logger.info(f"[PROCESSED] Gift detected and processed")
            else:
                display_text = (text[:60] + '...') if len(text) > 60 else text
                if not display_text and message.media:
                    display_text = "[Media]"
                logger.debug(f"{chat_title[:15]} | {sender_name}: {display_text}")

        except Exception as e:
            logger.debug(f"Handler error: {e}")

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
# MAIN
# ============================================================================
async def main():
    """Main entry point."""
    logger.info("=" * 50)
    logger.info("Telegram Gift Claimer v8.0")
    logger.info("=" * 50)
    
    validate_config()
    
    logger.info(f"Monitoring {len(TARGET_CHANNELS)} channel(s)")
    
    client = create_client()
    setup_handlers(client)
    
    try:
        await client.connect()
        
        if not await login_system(client):
            logger.error("Login failed!")
            return
        
        logger.info("Monitoring started... Press Ctrl+C to stop")
        await client.run_until_disconnected()
        
    except KeyboardInterrupt:
        logger.info("Stopping...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await client.disconnect()
        logger.info("Disconnected. Goodbye!")

if __name__ == "__main__":
    asyncio.run(main())
