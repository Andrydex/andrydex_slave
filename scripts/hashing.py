import hashlib


def generate_hash(content):

    return hashlib.md5(content.encode()).hexdigest()
