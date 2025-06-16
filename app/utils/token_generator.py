import secrets

def generate_unique_token():
    return secrets.token_urlsafe(16)
