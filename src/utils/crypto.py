"""
AES-256-GCM encryption utility matching the be-middlewares Go implementation.
"""

import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from utils.errors import CryptoError, DecryptionError

# Constants from be-middlewares/libs/apicrypto/helpers/aes.go
KEY_LENGTH = 32
NONCE_LENGTH = 16
DATA_SEPARATOR = "."


class MiloticCipher:
    """
    Handles AES-256-GCM encryption and decryption, producing a wire format
    compatible with the Go backend: `nonce.tag.ciphertext`.
    """

    def __init__(self, session_secret: str):
        if len(session_secret) < KEY_LENGTH:
            raise CryptoError(f"Session secret must be at least {KEY_LENGTH} bytes.")
        # Use the first 32 bytes of the secret, matching Go's `[]byte(secretKey)`
        self._key = session_secret[:KEY_LENGTH].encode("utf-8")
        self._aesgcm = AESGCM(self._key)

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypts a plaintext string into the `nonce.tag.ciphertext` wire format.
        A new 16-byte nonce is generated for each encryption.
        """
        try:
            nonce = os.urandom(NONCE_LENGTH)
            plaintext_bytes = plaintext.encode("utf-8")

            encrypted_bytes = self._aesgcm.encrypt(nonce, plaintext_bytes, None)

            # The tag is the last 16 bytes of the output from `encrypt`
            tag = encrypted_bytes[-16:]
            ciphertext = encrypted_bytes[:-16]

            # Encode all parts to Base64
            nonce_b64 = base64.b64encode(nonce).decode("utf-8")
            tag_b64 = base64.b64encode(tag).decode("utf-8")
            ciphertext_b64 = base64.b64encode(ciphertext).decode("utf-8")

            return f"{nonce_b64}{DATA_SEPARATOR}{tag_b64}{DATA_SEPARATOR}{ciphertext_b64}"
        except Exception as e:
            raise CryptoError("Failed to encrypt data.") from e

    def decrypt(self, wire_string: str) -> str:
        """
        Decrypts a `nonce.tag.ciphertext` wire string back to plaintext.
        """
        try:
            parts = wire_string.split(DATA_SEPARATOR)
            if len(parts) != 3:
                raise DecryptionError("Invalid encrypted payload format: expected 3 parts.")

            nonce_b64, tag_b64, ciphertext_b64 = parts

            nonce = base64.b64decode(nonce_b64)
            tag = base64.b64decode(tag_b64)
            ciphertext = base64.b64decode(ciphertext_b64)

            if len(nonce) != NONCE_LENGTH:
                raise DecryptionError(f"Invalid nonce length: expected {NONCE_LENGTH}.")

            # Re-assemble ciphertext and tag for decryption
            encrypted_bytes = ciphertext + tag

            decrypted_bytes = self._aesgcm.decrypt(nonce, encrypted_bytes, None)

            return decrypted_bytes.decode("utf-8")
        except DecryptionError:
            raise
        except Exception as e:
            raise DecryptionError("Failed to decrypt data.") from e

    def encrypt_json(self, data: dict) -> dict:
        """Serializes a dict, encrypts it, and wraps it in the `{"payload": ...}` structure."""
        plaintext = json.dumps(data, separators=(",", ":"))
        encrypted_str = self.encrypt(plaintext)
        return {"payload": encrypted_str}

    def decrypt_json(self, wrapper: dict) -> dict:
        """Extracts the payload from the wrapper, decrypts, and deserializes to a dict."""
        if "payload" not in wrapper or not isinstance(wrapper["payload"], str):
            raise DecryptionError("Encrypted response is missing 'payload' field.")

        decrypted_str = self.decrypt(wrapper["payload"])
        return json.loads(decrypted_str)
