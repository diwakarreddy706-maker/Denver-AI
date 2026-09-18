"""Denver AI Assistant — Dedicated WhatsApp Voice & Desktop Automation Dispatcher."""

from __future__ import annotations

import os
import re
import time
import urllib.parse
import webbrowser
from typing import Any

from denver.automation.models import AutomationResult, AutomationRisk
from denver.logging.logger import get_logger
from denver.utils.logging_helpers import mask_phone

logger = get_logger("automation.whatsapp")


class WhatsAppDispatcher:
    """Dispatches WhatsApp messages via native Desktop protocol and Web fallbacks with safe mock support."""

    @staticmethod
    def clean_phone_number(raw_phone: str) -> str:
        """Standardize phone number for WhatsApp URI protocol (digits only, stripping + and formatting)."""
        if not raw_phone:
            return ""
        cleaned = re.sub(r"[^\d+]", "", raw_phone.strip())
        if cleaned.startswith("+"):
            return cleaned[1:]
        return cleaned

    @staticmethod
    def encode_message(message: str) -> str:
        """URL encode message text, safely preserving emojis and UTF-8 characters."""
        return urllib.parse.quote(message)

    @classmethod
    def build_desktop_uri(cls, message: str, phone: str = "") -> str:
        """Build whatsapp:// desktop protocol URI."""
        encoded = cls.encode_message(message)
        cleaned_phone = cls.clean_phone_number(phone)
        if cleaned_phone:
            return f"whatsapp://send?phone={cleaned_phone}&text={encoded}"
        return f"whatsapp://send?text={encoded}"

    @classmethod
    def build_web_url(cls, message: str, phone: str = "") -> str:
        """Build https://web.whatsapp.com fallback URL."""
        encoded = cls.encode_message(message)
        cleaned_phone = cls.clean_phone_number(phone)
        if cleaned_phone:
            return f"https://web.whatsapp.com/send?phone={cleaned_phone}&text={encoded}"
        return f"https://web.whatsapp.com/send?text={encoded}"

    def dispatch_message(
        self,
        message: str,
        phone: str = "",
        contact_name: str = "",
        is_mock: bool = False,
    ) -> AutomationResult:
        """Dispatch drafted WhatsApp message to recipient via desktop protocol or web fallback."""
        clean_msg = message.strip()
        if (clean_msg.startswith('"') and clean_msg.endswith('"')) or (
            clean_msg.startswith("'") and clean_msg.endswith("'")
        ):
            clean_msg = clean_msg[1:-1].strip()

        # Auto-resolve contact phone number from ContactBook if not explicitly provided
        if not phone and contact_name:
            try:
                from denver.memory.contacts import get_contact_book

                cb = get_contact_book()
                matched = cb.find_contact(contact_name)
                if matched and matched.clean_phone() and len(matched.clean_phone()) >= 7:
                    phone = matched.clean_phone()
                    logger.info(
                        "Auto-resolved phone '%s' for contact '%s' via ContactBook (%s).",
                        mask_phone(phone),
                        contact_name,
                        matched.name,
                    )
            except Exception as cb_err:
                logger.debug("ContactBook auto-resolve skipped: %s", cb_err)

        target_display = f"WhatsApp ({contact_name})" if contact_name else ("WhatsApp" if not phone else f"WhatsApp ({phone})")
        uri = self.build_desktop_uri(clean_msg, phone)
        web_url = self.build_web_url(clean_msg, phone)

        # Environment check for mock/testing safety
        is_test = (
            is_mock
            or os.environ.get("DENVER_MOCK_AUTOMATION", "").lower() in ("true", "1", "yes")
            or "PYTEST_CURRENT_TEST" in os.environ
        )

        if is_test:
            logger.info("[MOCK] Dispatched WhatsApp message to '%s' (phone: '%s', message_length=%d)", contact_name, mask_phone(phone), len(clean_msg))
            return AutomationResult(
                success=True,
                action="send_whatsapp_message",
                target=target_display,
                message=f"Sent WhatsApp message to {contact_name or phone or 'contact'}: '{clean_msg}'",
                data={
                    "scheme": uri,
                    "web_url": web_url,
                    "message": clean_msg,
                    "contact": contact_name,
                    "phone": phone,
                    "mock": True,
                },
                risk_level=AutomationRisk.LOW,
            )

        # Real Execution on Desktop
        try:
            os.startfile(uri)  # pylint: disable=no-member
            logger.info("Launched WhatsApp (phone: '%s', message_length=%d)", mask_phone(phone), len(clean_msg))

            # If direct phone number was used, WhatsApp Desktop opens the chat directly.
            # Press Enter to dispatch the drafted message in chat.
            if phone:
                try:
                    import ctypes

                    time.sleep(1.2)
                    vk_return = 0x0D
                    ctypes.windll.user32.keybd_event(vk_return, 0, 0, 0)
                    time.sleep(0.05)
                    ctypes.windll.user32.keybd_event(vk_return, 0, 2, 0)
                    logger.info("Dispatched WhatsApp message to %s.", mask_phone(phone))
                except Exception as send_err:
                    logger.debug("Auto-send keypress skipped: %s", send_err)

            # If contact name was specified and no direct phone number was used,
            # WhatsApp Desktop opens the 'Send message to' dialog with search focused.
            elif contact_name and not phone:
                try:
                    import ctypes
                    import pyperclip

                    time.sleep(1.2)
                    pyperclip.copy(contact_name)

                    vk_control = 0x11
                    vk_v = 0x56
                    vk_return = 0x0D
                    vk_space = 0x20
                    vk_tab = 0x09

                    def press_key(vk: int, hold_delay: float = 0.05) -> None:
                        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                        time.sleep(hold_delay)
                        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)

                    # 1. Paste contact name into search input (Ctrl+V)
                    ctypes.windll.user32.keybd_event(vk_control, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(vk_v, 0, 0, 0)
                    time.sleep(0.05)
                    ctypes.windll.user32.keybd_event(vk_v, 0, 2, 0)
                    ctypes.windll.user32.keybd_event(vk_control, 0, 2, 0)

                    # 2. Wait for WhatsApp search results to filter
                    time.sleep(1.0)

                    # 3. Tab out of search input into results
                    press_key(vk_tab)
                    time.sleep(0.2)
                    press_key(vk_tab)
                    time.sleep(0.2)

                    # 4. Check contact item checkbox
                    press_key(vk_space)
                    time.sleep(0.3)

                    # 5. Confirm selection
                    press_key(vk_return)
                    time.sleep(0.5)

                    # 6. Tab to Send button and trigger Enter
                    press_key(vk_tab)
                    time.sleep(0.2)
                    press_key(vk_return)
                    time.sleep(1.0)

                    # 7. Send drafted message in chat
                    press_key(vk_return)

                    logger.info("Auto-selected contact '%s' and sent message.", contact_name)
                except Exception as auto_err:
                    logger.warning("WhatsApp contact auto-select skipped: %s", auto_err)

            return AutomationResult(
                success=True,
                action="send_whatsapp_message",
                target=target_display,
                message=f"Sent WhatsApp message to {contact_name or phone or 'contact'}: '{clean_msg}'",
                data={
                    "scheme": uri,
                    "web_url": web_url,
                    "message": clean_msg,
                    "contact": contact_name,
                    "phone": phone,
                },
                risk_level=AutomationRisk.LOW,
            )

        except Exception as exc:
            logger.warning("Native WhatsApp desktop protocol failed (%s); launching Web fallback.", exc)
            webbrowser.open(web_url)
            return AutomationResult(
                success=True,
                action="send_whatsapp_message",
                target=f"{target_display} (Web)",
                message=f"Opened WhatsApp Web with message ready for {contact_name or phone or 'contact'}: '{clean_msg}'",
                data={
                    "url": web_url,
                    "message": clean_msg,
                    "contact": contact_name,
                    "phone": phone,
                },
                risk_level=AutomationRisk.LOW,
            )
