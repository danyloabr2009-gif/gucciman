#!/usr/bin/env python3
"""
Professional Telegram Gift Claimer Bot
Author: Professional Developer
Version: 11.0 Pro
"""

import asyncio
import os
import sys
import time
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from dotenv import load_dotenv

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, 
    UserAlreadyParticipantError,
    UserPrivacyRestrictedError,
    ChatAdminRequiredError,
    ChannelPrivateError,
    BotMethodInvalidError
)
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import (
    InputPeerUser,
    InputPeerChat,
    InputPeerChannel,
    UpdateNewMessage,
    UpdateNewChannelMessage
)

# ============================================================================
# CONFIGURATION
# ============================================================================
load_dotenv()

# API Configuration
API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH', '')
SESSION_NAME = os.getenv('SESSION_NAME', 'gift_claimer_session')
STRING_SESSION = os.getenv('STRING_SESSION', '')

# Target Configuration
TARGET_CHANNELS = [int(x.strip()) for x in os.getenv('TARGET_CHANNELS', '').split(',') if x.strip()]
NOTIFY_USER = os.getenv('NOTIFY_USER', 'me')

# Bot Configuration
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '5'))
RETRY_DELAY = int(os.getenv('RETRY_DELAY', '10'))
PRELOAD_BOTS = [x.strip() for x in os.getenv('PRELOAD_BOTS', '').split(',') if x.strip()]

# ============================================================================
# DATA STRUCTURES
# ============================================================================
@dataclass
class Stats:
    messages_total: int = 0
    messages_with_buttons: int = 0
    gifts_detected: int = 0
    gifts_claimed: int = 0
    gifts_failed: int = 0
    subscriptions_completed: int = 0
    last_action_time: Optional[datetime] = None
    last_gift_time: Optional[datetime] = None
    restarts: int = 0

@dataclass
class ButtonInfo:
    text: str
    type: str  # 'callback', 'url', 'text'
    data: Optional[bytes] = None
    url: Optional[str] = None
    row_idx: int = 0
    btn_idx: int = 0

# ============================================================================
# UNIVERSAL TRIGGERS
# ============================================================================
class ButtonTriggers:
    """Universal button triggers for instant reaction"""
    
    # Standard giveaways
    GIVEAWAY_BUTTONS = [
        'участвовать', 'принять участие', 'участвую', 'участвую!',
        'participate', 'join', 'enter', 'take part'
    ]
    
    # Gift checks
    GIFT_CHECK_BUTTONS = [
        'активировать чек', 'получить', 'забрать', 'claim', 'get',
        'activate check', 'activate', 'receive', 'collect'
    ]
    
    # Fast click buttons
    FAST_CLICK_BUTTONS = [
        'тапп', 'тап', 'тык', 'забрать', 'go', 'tap', 'click'
    ]
    
    # Blind search keywords
    BLIND_SEARCH_KEYWORDS = [
        'первому', 'кто успеет', 'розыгрыш', 'first', 'fastest', 'giveaway'
    ]
    
    # Subscription buttons
    SUBSCRIPTION_BUTTONS = [
        'подписаться', 'подписка', 'subscribe', 'join channel'
    ]
    
    # Confirmation buttons
    CONFIRMATION_BUTTONS = [
        'я подписался', 'подписался', 'subscribed', 'проверить подписку'
    ]

# ============================================================================
# LOGGING SYSTEM
# ============================================================================
class Logger:
    """Professional logging system with Saved Messages integration"""
    
    def __init__(self, client: TelegramClient):
        self.client = client
        self.stats = Stats()
        
    def _format_message(self, message: str) -> str:
        """Format message with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        return f"[{timestamp}] {message}"
    
    def info(self, message: str):
        """Log info message"""
        formatted = self._format_message(message)
        print(formatted)
        
    def warning(self, message: str):
        """Log warning message"""
        formatted = self._format_message(f"[WARNING] {message}")
        print(formatted)
        
    def error(self, message: str):
        """Log error message"""
        formatted = self._format_message(f"[ERROR] {message}")
        print(formatted)
        
    def success(self, message: str):
        """Log success message"""
        formatted = self._format_message(f"[SUCCESS] {message}")
        print(formatted)
        
    async def log_to_saved(self, action: str, chat_name: str, details: str = ""):
        """Send log to Saved Messages"""
        try:
            message = f"[GIFT] Gift Claimer : {action} | {chat_name}"
            if details:
                message += f" | {details}"
            
            await self.client.send_message('me', message)
        except Exception as e:
            self.warning(f"Failed to log to Saved Messages: {e}")

# ============================================================================
# BUTTON PROCESSOR
# ============================================================================
class ButtonProcessor:
    """Professional button processing system"""
    
    def __init__(self, logger: Logger):
        self.logger = logger
        self.triggers = ButtonTriggers()
        
    def analyze_message(self, message_text: str, buttons: List) -> Dict:
        """Analyze message and determine action strategy"""
        message_text_lower = message_text.lower()
        
        analysis = {
            'has_giveaway_buttons': False,
            'has_gift_check_buttons': False,
            'has_fast_click_buttons': False,
            'has_subscription_buttons': False,
            'has_confirmation_buttons': False,
            'needs_blind_search': False,
            'target_buttons': [],
            'subscription_buttons': [],
            'confirmation_buttons': []
        }
        
        # Check for blind search keywords
        if any(keyword in message_text_lower for keyword in self.triggers.BLIND_SEARCH_KEYWORDS):
            analysis['needs_blind_search'] = True
            self.logger.info("🔍 Обнаружен слепой поиск - нажимаю любую кнопку")
        
        # Analyze buttons
        for row_idx, row in enumerate(buttons):
            for btn_idx, btn in enumerate(row):
                btn_text = (btn.text or "").lower()
                button_info = ButtonInfo(
                    text=btn.text or "",
                    type='callback' if btn.data else 'url' if btn.url else 'text',
                    data=btn.data,
                    url=btn.url,
                    row_idx=row_idx,
                    btn_idx=btn_idx
                )
                
                # Check giveaway buttons
                if any(trigger in btn_text for trigger in self.triggers.GIVEAWAY_BUTTONS):
                    analysis['has_giveaway_buttons'] = True
                    analysis['target_buttons'].append(button_info)
                    self.logger.info(f"🎉 Найдена кнопка розыгрыша: '{btn.text}'")
                
                # Check gift check buttons
                elif any(trigger in btn_text for trigger in self.triggers.GIFT_CHECK_BUTTONS):
                    analysis['has_gift_check_buttons'] = True
                    analysis['target_buttons'].append(button_info)
                    self.logger.info(f"🎁 Найдена кнопка чека: '{btn.text}'")
                
                # Check fast click buttons
                elif any(trigger in btn_text for trigger in self.triggers.FAST_CLICK_BUTTONS):
                    analysis['has_fast_click_buttons'] = True
                    analysis['target_buttons'].append(button_info)
                    self.logger.info(f"⚡ Найдена быстрая кнопка: '{btn.text}'")
                
                # Check subscription buttons
                elif any(trigger in btn_text for trigger in self.triggers.SUBSCRIPTION_BUTTONS):
                    analysis['has_subscription_buttons'] = True
                    analysis['subscription_buttons'].append(button_info)
                    self.logger.info(f"📡 Найдена кнопка подписки: '{btn.text}'")
                
                # Check confirmation buttons
                elif any(trigger in btn_text for trigger in self.triggers.CONFIRMATION_BUTTONS):
                    analysis['has_confirmation_buttons'] = True
                    analysis['confirmation_buttons'].append(button_info)
                    self.logger.info(f"✓ Найдена кнопка подтверждения: '{btn.text}'")
        
        # Blind search: if keywords found but no specific buttons, target all buttons
        if analysis['needs_blind_search'] and not analysis['target_buttons']:
            for row_idx, row in enumerate(buttons):
                for btn_idx, btn in enumerate(row):
                    if btn.data or btn.url:  # Only interactive buttons
                        button_info = ButtonInfo(
                            text=btn.text or f"Button[{row_idx}:{btn_idx}]",
                            type='callback' if btn.data else 'url' if btn.url else 'text',
                            data=btn.data,
                            url=btn.url,
                            row_idx=row_idx,
                            btn_idx=btn_idx
                        )
                        analysis['target_buttons'].append(button_info)
        
        return analysis
    
    async def press_button(self, client: TelegramClient, chat_id: int, message_id: int, button_info: ButtonInfo) -> bool:
        """Press a button with error handling"""
        try:
            if button_info.type == 'callback' and button_info.data:
                await client(GetBotCallbackAnswerRequest(
                    peer=chat_id,
                    msg_id=message_id,
                    data=button_info.data
                ))
            elif button_info.type == 'url' and button_info.url:
                # Handle URL buttons
                try:
                    # Extract parameters from URL
                    url = button_info.url
                    
                    # Check if it's a Telegram bot URL with start parameter
                    if 't.me/' in url and ('start=' in url or 'startapp=' in url):
                        # Extract start parameter
                        if 'start=' in url:
                            start_param = url.split('start=')[1].split('&')[0]
                        elif 'startapp=' in url:
                            start_param = url.split('startapp=')[1].split('&')[0]
                        
                        # Send /start command to bot
                        bot_username = url.split('t.me/')[1].split('?')[0]
                        await self.client.send_message(bot_username, f'/start {start_param}')
                        
                        self.logger.success(f"[SUCCESS] URL обработан: @{bot_username}")
                        return True
                        
                except Exception as e:
                    self.logger.error(f"[ERROR] Ошибка обработки URL: {e}")
                    return False
            else:
                return False
            
            self.logger.success(f"[SUCCESS] Кнопка '{button_info.text}' нажата успешно")
            return True
            
        except FloodWaitError as e:
            wait_time = e.seconds
            self.logger.warning(f"[FLOOD] FloodWait: жду {wait_time} секунд...")
            await asyncio.sleep(wait_time)
            return False
            
        except Exception as e:
            self.logger.error(f"[ERROR] Ошибка нажатия кнопки: {e}")
            return False

# ============================================================================
# SUBSCRIPTION MANAGER
# ============================================================================
class SubscriptionManager:
    """Handle subscription requirements"""
    
    def __init__(self, logger: Logger):
        self.logger = logger
    
    async def subscribe_to_channels(self, client: TelegramClient, buttons: List[ButtonInfo]) -> int:
        """Subscribe to all channels from subscription buttons"""
        subscribed_count = 0
        
        for button_info in buttons:
            if button_info.type == 'url' and button_info.url:
                try:
                    # Extract channel from URL
                    if 't.me/' in button_info.url:
                        channel_username = button_info.url.split('t.me/')[1].split('?')[0]
                        
                        # Join channel
                        await client(JoinChannelRequest(
                            channel=channel_username
                        ))
                        
                        subscribed_count += 1
                        self.logger.success(f"[SUBSCRIBE] Успешная подписка на @{channel_username}")
                        
                        # Log to saved messages
                        await self.logger.log_to_saved(
                            f"Успешная подписка на @{channel_username}",
                            "Subscription Manager"
                        )
                        
                except UserAlreadyParticipantError:
                    self.logger.info(f"[INFO] Уже подписан на @{channel_username}")
                    subscribed_count += 1
                    
                except (ChannelPrivateError, ChatAdminRequiredError) as e:
                    self.logger.warning(f"[WARNING] Не удалось подписаться на @{channel_username}: {e}")
                    
                except Exception as e:
                    self.logger.error(f"[ERROR] Ошибка подписки на @{channel_username}: {e}")
        
        return subscribed_count

# ============================================================================
# MAIN BOT CLASS
# ============================================================================
class GiftClaimerBot:
    """Main professional gift claimer bot"""
    
    def __init__(self):
        self.client = None
        self.logger = None
        self.button_processor = None
        self.subscription_manager = None
        self.stats = Stats()
        
    async def initialize(self):
        """Initialize bot components"""
        # Create client
        if STRING_SESSION:
            self.client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
        else:
            self.client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        
        # Initialize components
        self.logger = Logger(self.client)
        self.button_processor = ButtonProcessor(self.logger)
        self.subscription_manager = SubscriptionManager(self.logger)
        
        # Setup event handlers
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup message handlers"""
        
        @self.client.on(events.NewMessage(chats=TARGET_CHANNELS))
        async def handle_new_message(event):
            """Handle new messages with instant reaction"""
            await self.process_message(event)
    
    async def process_message(self, event):
        """Process incoming message with professional logic"""
        message = event.message
        self.stats.messages_total += 1
        self.stats.last_action_time = datetime.now()
        
        # Get chat info
        try:
            chat = await self.client.get_entity(event.chat_id)
            chat_name = getattr(chat, 'title', getattr(chat, 'first_name', f"ID:{event.chat_id}"))
        except Exception:
            chat_name = f"ID:{event.chat_id}"
        
        # Log message monitoring
        message_preview = (message.text or "")[:50]
        self.logger.info(f"👁️ Мониторинг: {chat_name} | #{message.id} | '{message_preview}...'")
        
        # Check if message has buttons
        if not message.buttons:
            return
        
        self.stats.messages_with_buttons += 1
        button_count = sum(len(row) for row in message.buttons)
        self.logger.info(f"🔘 Найдено кнопок: {button_count}")
        
        # Analyze message and buttons
        analysis = self.button_processor.analyze_message(message.text or "", message.buttons)
        
        # Strategy 1: Handle subscriptions first
        if analysis['has_subscription_buttons']:
            self.logger.info("📡 Обнаружены кнопки подписки - обрабатываю...")
            subscribed_count = await self.subscription_manager.subscribe_to_channels(
                self.client, analysis['subscription_buttons']
            )
            
            if subscribed_count > 0:
                self.stats.subscriptions_completed += subscribed_count
                await self.logger.log_to_saved(
                    f"Подписка на {subscribed_count} каналов завершена",
                    chat_name
                )
                
                # Wait a bit and retry main action
                await asyncio.sleep(1)
        
        # Strategy 2: Handle main target buttons
        if analysis['target_buttons']:
            for button_info in analysis['target_buttons']:
                success = await self.button_processor.press_button(
                    self.client, event.chat_id, message.id, button_info
                )
                
                if success:
                    self.stats.gifts_claimed += 1
                    self.stats.last_gift_time = datetime.now()
                    
                    # Log to saved messages
                    await self.logger.log_to_saved(
                        f"Нажата кнопка '{button_info.text}'",
                        chat_name,
                        datetime.now().strftime("%H:%M:%S")
                    )
                    
                    return  # Success, stop processing
        
        # Strategy 3: Handle confirmation buttons
        if analysis['has_confirmation_buttons']:
            for button_info in analysis['confirmation_buttons']:
                await self.button_processor.press_button(
                    self.client, event.chat_id, message.id, button_info
                )
    
    async def run(self):
        """Main bot execution loop"""
        await self.initialize()
        
        self.logger.info("=" * 60)
        self.logger.info("[GIFT] Gift Claimer Bot v11.0 Pro - STARTING")
        self.logger.info("=" * 60)
        self.logger.info(f"[MONITOR] Каналов: {len(TARGET_CHANNELS)}")
        self.logger.info(f"[TARGET] Кнопки: Розыгрыши, Чеки, Fast Click")
        self.logger.info(f"[LOGGING] Включено (Saved Messages)")
        self.logger.info("=" * 60)
        
        # Start client
        try:
            await self.client.start()
        except Exception as e:
            self.logger.error(f"Failed to start client: {e}")
            return
        self.logger.success("[SUCCESS] Бот успешно запущен!")
        
        # Log startup to saved messages
        await self.logger.log_to_saved(
            "Бот запущен и готов к работе",
            "System",
            f"Каналы: {len(TARGET_CHANNELS)}"
        )
        
        # Keep bot running
        try:
            await self.client.run_until_disconnected()
        except KeyboardInterrupt:
            self.logger.info("[STOP] Остановка по запросу пользователя...")
        finally:
            await self.client.disconnect()
            self.logger.info("[STOP] Бот остановлен")

# ============================================================================
# MAIN EXECUTION
# ============================================================================
async def main():
    """Main entry point"""
    bot = GiftClaimerBot()
    await bot.run()

if __name__ == "__main__":
    # Validate configuration
    if not API_ID or not API_HASH:
        print("ERROR: API_ID и API_HASH должны быть указаны в .env файле")
        sys.exit(1)
    
    if not TARGET_CHANNELS:
        print("ERROR: TARGET_CHANNELS должны быть указаны в .env файле")
        sys.exit(1)
    
    # Run bot
    asyncio.run(main())
