import os
import time
from secrets import token_bytes


def _fallback_uuid7_hex() -> str:
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    random_bytes = bytearray(token_bytes(10))
    random_bytes[0] = (random_bytes[0] & 0x0F) | 0x70
    random_bytes[2] = (random_bytes[2] & 0x3F) | 0x80
    value = timestamp_ms.to_bytes(6, "big") + bytes(random_bytes)
    return value.hex()


def uuid7_hex() -> str:
    force_fallback = os.getenv("UUID7_FORCE_FALLBACK", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if not force_fallback:
        try:
            import uuid6  # type: ignore

            return uuid6.uuid7().hex
        except Exception:
            pass
    return _fallback_uuid7_hex()

