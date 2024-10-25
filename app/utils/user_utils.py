import hashlib


def generate_short_user_id(user_id: int | None) -> str:
    """
    Generate a short hexadecimal representation of the user_id.
    
    Args:
        user_id (int | None): The original user ID.
    
    Returns:
        str: A short hexadecimal string representing the user_id.
    """
    if user_id is None:
        return 'anonymous'
    
    # Convert user_id to bytes and hash it
    user_id_bytes = str(user_id).encode('utf-8')
    hash_object = hashlib.sha256(user_id_bytes)
    
    # Take the first 8 characters of the hexadecimal representation
    return hash_object.hexdigest()[:8]
