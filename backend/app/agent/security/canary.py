import hashlib
import hmac


def generate_canary_token(thread_id: str, secret: str) -> str:
    """Generate a deterministic canary token for a thread.

    Returns a 16-character hex string derived from HMAC-SHA256(secret, thread_id).
    """
    return hmac.new(secret.encode(), thread_id.encode(), hashlib.sha256).hexdigest()[
        :16
    ]
