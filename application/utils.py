import random
import string


def generate_otp(length=21):
    characters = string.ascii_letters + string.digits
    otp = "".join(random.choice(characters) for i in range(length))
    return otp
