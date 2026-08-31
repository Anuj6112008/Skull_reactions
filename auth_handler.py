"""
Interactive Telegram Authentication Handler (OTP + 2FA)
Compatible with Python 3.11
"""

from typing import Tuple, Dict, Any
from pyrogram import Client
from pyrogram.errors import (
    SessionPasswordNeeded,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    PasswordHashInvalid,
    PhoneNumberInvalid,
    FloodWait
)
import config


class AuthHandler:
    def __init__(self) -> None:
        # Temporary storage for active in-memory login clients per admin
        self.active_auths: Dict[int, Dict[str, Any]] = {}

    async def request_otp(self, admin_id: int, phone_number: str) -> Tuple[bool, str]:
        """
        Initializes an in-memory client and sends an OTP code to the given phone number.
        """
        # Clean up any existing stale auth session for this admin
        await self.cleanup(admin_id)

        # Standardize phone number formatting
        clean_phone = phone_number.strip().replace(" ", "").replace("-", "")

        client = Client(
            name=f"auth_temp_{admin_id}",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            in_memory=True
        )

        try:
            await client.connect()
            code_info = await client.send_code(clean_phone)
            
            self.active_auths[admin_id] = {
                "client": client,
                "phone": clean_phone,
                "code_hash": code_info.phone_code_hash
            }
            return True, "OTP successfully sent to the account."
        except PhoneNumberInvalid:
            await client.disconnect()
            return False, "Invalid phone number format. Include country code (e.g., +919876543210)."
        except FloodWait as e:
            await client.disconnect()
            return False, f"Telegram rate limit: Wait {e.value} seconds before requesting again."
        except Exception as e:
            await client.disconnect()
            return False, f"Telegram Error: {str(e)}"

    async def submit_otp(self, admin_id: int, otp_code: str) -> Tuple[str, str]:
        """
        Verifies the OTP code. Returns status code and session string or prompt.
        """
        session_data = self.active_auths.get(admin_id)
        if not session_data:
            return "EXPIRED", "Session expired or not found. Please start login again."

        client: Client = session_data["client"]
        phone: str = session_data["phone"]
        code_hash: str = session_data["code_hash"]
        clean_otp = otp_code.strip().replace(" ", "").replace("-", "")

        try:
            await client.sign_in(phone, code_hash, clean_otp)
            session_str = await client.export_session_string()
            await client.disconnect()
            del self.active_auths[admin_id]
            return "SUCCESS", session_str
        except SessionPasswordNeeded:
            return "2FA_REQUIRED", "Two-Step Verification (2FA) is enabled on this account."
        except PhoneCodeInvalid:
            return "INVALID_OTP", "Incorrect OTP code. Please check and re-enter."
        except PhoneCodeExpired:
            await self.cleanup(admin_id)
            return "EXPIRED", "OTP code has expired. Please restart the process."
        except Exception as e:
            return "ERROR", f"Sign-in error: {str(e)}"

    async def submit_2fa(self, admin_id: int, password: str) -> Tuple[str, str]:
        """
        Verifies the 2FA password and extracts the session string.
        """
        session_data = self.active_auths.get(admin_id)
        if not session_data:
            return "EXPIRED", "Session expired. Please restart login."

        client: Client = session_data["client"]

        try:
            await client.check_password(password.strip())
            session_str = await client.export_session_string()
            await client.disconnect()
            del self.active_auths[admin_id]
            return "SUCCESS", session_str
        except PasswordHashInvalid:
            return "INVALID_PWD", "Incorrect 2FA password. Please try again."
        except Exception as e:
            return "ERROR", f"2FA verification failed: {str(e)}"

    async def cleanup(self, admin_id: int) -> None:
        """Safely disconnects and cleans up temp sessions."""
        if admin_id in self.active_auths:
            try:
                await self.active_auths[admin_id]["client"].disconnect()
            except Exception:
                pass
            del self.active_auths[admin_id]


# Singleton instance
auth_system = AuthHandler()