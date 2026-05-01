import hashlib

def generate_hash(testo):
    # Genera un ID univoco e immutabile basato sul titolo
    return hashlib.md5(str(testo).encode('utf-8')).hexdigest()[:10]
