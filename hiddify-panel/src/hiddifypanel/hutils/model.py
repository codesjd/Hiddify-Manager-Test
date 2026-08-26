def gen_username(model) -> None:
    from hiddifypanel import hutils
    if model.username:
        return
    base_username = model.name or ''
    minimum_username_length = 10

    if len(base_username) < minimum_username_length:
        base_username += hutils.random.get_random_string(minimum_username_length - len(base_username), minimum_username_length)

    if len(base_username) > 100:
        base_username = base_username[0:100]
    model.username = base_username

    while not model.is_username_unique():
        rand_str = hutils.random.get_random_string(2, 4)
        model.username += rand_str


def gen_password(model) -> None:
    from hiddifypanel import hutils
    from werkzeug.security import generate_password_hash

    is_hashed = model.password and (model.password.startswith('scrypt:') or model.password.startswith('pbkdf2:'))
    if not model.password or (not is_hashed and len(model.password) < 16):
        model.password = hutils.random.get_random_password(length=16)

    is_hashed = model.password and (model.password.startswith('scrypt:') or model.password.startswith('pbkdf2:'))
    if not is_hashed:
        model.password = generate_password_hash(model.password)


def gen_wg_keys(model) -> None:
    from hiddifypanel import hutils
    if not model.wg_pk or not model.wg_pub or not model.wg_psk:
        model.wg_pk, model.wg_pub, model.wg_psk = hutils.crypto.get_wg_private_public_psk_pair()


def gen_ed25519_keys(model) -> None:
    from hiddifypanel import hutils
    if not model.ed25519_private_key or not model.ed25519_public_key:
        model.ed25519_private_key, model.ed25519_public_key = hutils.crypto.get_ed25519_private_public_pair()
