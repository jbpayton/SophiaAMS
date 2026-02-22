"""
Telegram adapter — receives messages from Telegram and routes responses back.

Uses python-telegram-bot (async). Enabled via config when TELEGRAM_BOT_TOKEN
is set and telegram.enabled is true.
"""

import asyncio
import logging
from typing import List, Optional, Set

from adapters.base import EventSourceAdapter
from event_bus import EventBus
from event_types import Event, EventPriority, EventType

logger = logging.getLogger(__name__)

try:
    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False


class TelegramAdapter(EventSourceAdapter):
    """
    Telegram bot that forwards incoming messages as events and
    sends agent responses back to the chat.
    """

    def __init__(
        self,
        bus: EventBus,
        token: str,
        allowed_chat_ids: Optional[List[int]] = None,
    ):
        super().__init__(bus)
        if not HAS_TELEGRAM:
            raise ImportError(
                "python-telegram-bot is required for the Telegram adapter. "
                "Install it with: pip install python-telegram-bot"
            )

        self.token = token
        self.allowed_chat_ids: Set[int] = set(allowed_chat_ids or [])
        self._app: Optional[Application] = None

        # Map event_id -> chat_id so we can route responses
        self._pending_chat_ids: dict[str, int] = {}

    async def start(self) -> None:
        """Build and start the Telegram bot."""
        self._app = (
            Application.builder()
            .token(self.token)
            .build()
        )

        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        logger.info("[TelegramAdapter] Started polling")

    async def stop(self) -> None:
        """Shut down the Telegram bot."""
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("[TelegramAdapter] Stopped")

    # ------------------------------------------------------------------
    # Telegram handlers
    # ------------------------------------------------------------------

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        if self.allowed_chat_ids and chat_id not in self.allowed_chat_ids:
            await update.message.reply_text("Access denied.")
            return
        await update.message.reply_text("Hi! I'm Sophia. Send me a message.")

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id

        if self.allowed_chat_ids and chat_id not in self.allowed_chat_ids:
            logger.warning(f"[TelegramAdapter] Blocked message from chat_id={chat_id}")
            return

        text = update.message.text
        session_id = f"telegram_{chat_id}"

        event = Event(
            event_type=EventType.CHAT_MESSAGE,
            payload={"session_id": session_id, "content": text},
            priority=EventPriority.USER_DIRECT,
            source_channel="telegram",
            reply_to=str(chat_id),
        )

        self._pending_chat_ids[event.event_id] = chat_id

        # Use threadsafe put since telegram-bot callbacks may not share our loop
        self.bus.put_threadsafe(event)

        logger.info(f"[TelegramAdapter] Message from chat_id={chat_id}: {text[:80]}")

    # ------------------------------------------------------------------
    # Response routing
    # ------------------------------------------------------------------

    async def handle_response(self, event: Event, response: str) -> None:
        """Send the agent's response back to the Telegram chat."""
        chat_id = self._pending_chat_ids.pop(event.event_id, None)
        if chat_id is None:
            # Fall back to reply_to field
            chat_id = int(event.reply_to) if event.reply_to else None

        if chat_id is None or self._app is None:
            logger.warning(f"[TelegramAdapter] Cannot route response for event {event.event_id}")
            return

        # Telegram has a 4096-char limit per message
        for i in range(0, len(response), 4096):
            await self._app.bot.send_message(chat_id=chat_id, text=response[i : i + 4096])

        logger.info(f"[TelegramAdapter] Sent response to chat_id={chat_id}")
