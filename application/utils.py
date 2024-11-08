import random
import string
import hashlib

def generate_otp(length=21):
    characters = string.ascii_letters + string.digits
    otp = "".join(random.choice(characters) for i in range(length))
    return otp

def hash_email_otp(email, otp):
    return hashlib.sha256((email + otp).encode()).hexdigest()
