import os
import hashlib
import hmac

# In a real system, this should be loaded from an environment variable or a secure vault
SECRET_KEY = os.getenv("EXTRACTOR_SYSTEM_KEY", "default-secret-key-change-me-1234567890123456")

def hash_token(token: str) -> str:
    """
    Creates a non-reversible hash of the token using HMAC-SHA256 
    with the EXTRACTOR_SYSTEM_KEY as the secret key.
    """
    key = SECRET_KEY.encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()
