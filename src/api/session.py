"""
Handles the creation of the RSA-encrypted X-API-Encryption-Key header.
"""

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from utils.errors import CryptoError


def _load_public_key(pem_or_der_b64: str):
    """
    Loads an RSA public key from either a full PEM string or a base64-encoded
    DER body, matching the format from be-middlewares.
    """
    if "-----BEGIN" not in pem_or_der_b64:
        # Assumes base64-encoded DER key body, needs PEM wrapping
        pem_data = (
            f"-----BEGIN PUBLIC KEY-----\n{pem_or_der_b64}\n-----END PUBLIC KEY-----"
        ).encode()
    else:
        pem_data = pem_or_der_b64.encode("utf-8")

    try:
        return serialization.load_pem_public_key(pem_data)
    except Exception as e:
        raise CryptoError("Failed to load or parse RSA public key.") from e


class SessionKeyProvider:
    """
    Encrypts the AES session secret using the backend's RSA public key to
    create the value for the X-API-Encryption-Key header.
    """

    def __init__(self, rsa_public_key_str: str):
        self._public_key = _load_public_key(rsa_public_key_str)

    def encrypt_session_for_header(self, session_secret: str) -> str:
        """
        Encrypts the session secret with the loaded RSA public key using
        RSA-OAEP-SHA256, then base64 encodes the result.
        """
        try:
            ciphertext = self._public_key.encrypt(
                session_secret.encode("utf-8"),
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
            return base64.b64encode(ciphertext).decode("utf-8")
        except Exception as e:
            raise CryptoError("Failed to RSA-encrypt session secret for header.") from e
