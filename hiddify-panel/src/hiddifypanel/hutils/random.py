import random
import secrets
import string
from hiddifypanel.models import hconfig, ConfigEnum

# get_random_string/get_random_password/random_case feed security-relevant
# secrets (admin/user panel path secrets, l2tp_psk, account passwords), so
# they must use a CSPRNG rather than the default (Mersenne Twister) `random`.
_secure_random = random.SystemRandom()


def get_random_string(min_: int = 10, max_: int = 30) -> str:
    # With combination of lower and upper case
    length = _secure_random.randint(min_, max_)
    characters = string.ascii_letters + string.digits
    result_str = ''.join(secrets.choice(characters) for i in range(length))
    return result_str


def get_random_password(length: int = 16) -> str:
    '''Retunrns a random password with fixed length'''
    characters = string.ascii_letters + string.digits  # + '-'
    while True:
        passwd = ''.join(secrets.choice(characters) for i in range(length))
        if (any(c.islower() for c in passwd) and any(c.isupper() for c in passwd) and sum(c.isdigit() for c in passwd) > 1):
            return passwd


def __is_port_in_range(port, start_port: int | str | None, count: int):
    if start_port is None:
        return False
    start_port = int(start_port)
    if port < start_port:
        return False

    if port > start_port + count:
        return False
    return True


def __is_in_used_port(port):
    for k in ConfigEnum:
        if "port" in k:
                for p in (hconfig(k) or "").split(","):
                    if p and __is_port_in_range(port, p, 100):
                        return True
    
    for p in [443, 80, 9000, 10085, 10086]:
        if __is_port_in_range(port, p, 100):
            return True
    return False


def get_random_unused_port():
    port = random.randint(11000, 60000)
    while __is_in_used_port(port):
        port = random.randint(11000, 60000)
    return port


def random_case(string):
    return ''.join(secrets.choice((str.upper, str.lower))(c) for c in string)
