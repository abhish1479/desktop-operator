import os
try:
    import keyring  # pip install keyring
except Exception:
    keyring = None

def get_secret(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name)
    if val:
        return val
    if keyring:
        try:
            return keyring.get_password("desktop-operator", name)
        except Exception:
            pass
    return default
