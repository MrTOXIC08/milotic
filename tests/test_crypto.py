import pytest

from utils.crypto import MiloticCipher
from utils.errors import CryptoError, DecryptionError

# Use a 32-byte key for AES-256
SECRET_KEY = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def cipher() -> MiloticCipher:
    return MiloticCipher(SECRET_KEY)


def test_cipher_round_trip(cipher: MiloticCipher):
    """Test that encrypting and then decrypting a message yields the original."""
    original_text = '{"message": "hello, world", "value": 123}'

    encrypted = cipher.encrypt(original_text)
    assert isinstance(encrypted, str)
    assert len(encrypted.split(".")) == 3

    decrypted = cipher.decrypt(encrypted)
    assert decrypted == original_text


def test_json_wrapper_round_trip(cipher: MiloticCipher):
    """Test the full JSON-in, JSON-out flow."""
    original_data = {"symbol": "BTC", "amount": 1.5, "nested": {"a": True}}

    encrypted_wrapper = cipher.encrypt_json(original_data)
    assert "payload" in encrypted_wrapper
    assert len(encrypted_wrapper["payload"].split(".")) == 3

    decrypted_data = cipher.decrypt_json(encrypted_wrapper)
    assert decrypted_data == original_data


def test_decryption_failure_bad_format(cipher: MiloticCipher):
    """Test that malformed wire strings raise DecryptionError."""
    with pytest.raises(DecryptionError, match="Invalid encrypted payload format"):
        cipher.decrypt("part1.part2")


def test_decryption_failure_bad_base64(cipher: MiloticCipher):
    """Test that bad base64 encoding raises DecryptionError."""
    with pytest.raises(DecryptionError, match="Failed to decrypt data"):
        cipher.decrypt("not-b64.not-b64.not-b64")


def test_decryption_failure_wrong_key():
    """Test that decrypting with a different key fails."""
    cipher1 = MiloticCipher(SECRET_KEY)
    cipher2 = MiloticCipher("another-key-that-is-32-bytes-long")

    encrypted = cipher1.encrypt("my secret message")

    with pytest.raises(DecryptionError, match="Failed to decrypt data"):
        cipher2.decrypt(encrypted)


def test_invalid_key_length():
    """Test that initializing with a key shorter than 32 bytes raises CryptoError."""
    with pytest.raises(CryptoError, match="must be at least 32 bytes"):
        MiloticCipher("shortkey")


# --- Golden Test Vector ---
# This vector should be generated from the Go implementation using the same key.
# It ensures byte-for-byte compatibility between the Python and Go AES-GCM.
# To generate in Go (using be-middlewares/libs/apicrypto/helpers/aes.go):
#   payload := `{"test":"golden"}`
#   secretKey := "0123456789abcdef0123456789abcdef"
#   // Temporarily modify EncryptAES to use a fixed nonce for a reproducible test vector
#   // e.g., nonce := bytes.Repeat([]byte{0x01}, 16)
#   // Then print the resulting nonce.tag.cipher string.

# NOTE: This is a placeholder. A real golden test requires a fixed nonce from Go.
# Without a fixed nonce, we cannot create a stable test vector.
# The current round-trip tests provide confidence, but cross-language
# compatibility must be verified with a shared test case.

# @pytest.mark.skip(reason="Requires fixed nonce from Go implementation to create a stable vector")
# def test_golden_vector_decryption(cipher: MiloticCipher):
#     go_encrypted_output = "AQEBAQEBAQEBAQEBAQEBAQ==.TAG_FROM_GO.CIPHERTEXT_FROM_GO"
#     expected_plaintext = `{"test":"golden"}`
#     decrypted = cipher.decrypt(go_encrypted_output)
#     assert decrypted == expected_plaintext
