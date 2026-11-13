"""فك تشفير القائمة البريدية data/recipients.enc (تُحفظ من صفحة «إدارة المنصة»).

الصيغة: AES-256-GCM بمفتاح مشتق من كلمة السر عبر PBKDF2-SHA256 (200,000 دورة).
كلمة السر في أسرار GitHub باسم RECIPIENTS_KEY. الملف المشفر وحده لا يكشف أي بريد.
"""
from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def decrypt(text: str, passphrase: str) -> list[dict]:
    o = json.loads(text)
    salt, iv, ct = (base64.b64decode(o[k]) for k in ("salt", "iv", "ct"))
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200000).derive(passphrase.encode("utf-8"))
    return json.loads(AESGCM(key).decrypt(iv, ct, None).decode("utf-8"))


def encrypt(items: list[dict], passphrase: str) -> str:
    import os
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200000).derive(passphrase.encode("utf-8"))
    ct = AESGCM(key).encrypt(iv, json.dumps(items, ensure_ascii=False).encode("utf-8"), None)
    b = lambda x: base64.b64encode(x).decode()  # noqa: E731
    return json.dumps({"v": 1, "kdf": "pbkdf2-sha256-200000", "alg": "aes-256-gcm", "salt": b(salt), "iv": b(iv), "ct": b(ct)}, indent=1) + "\n"
