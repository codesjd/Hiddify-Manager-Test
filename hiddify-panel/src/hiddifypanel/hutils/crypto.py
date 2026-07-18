import os
import subprocess
import sys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519, ed25519


def get_ed25519_private_public_pair():
    privkey = ed25519.Ed25519PrivateKey.generate()
    pubkey = privkey.public_key()
    priv_bytes = privkey.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = pubkey.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )
    return priv_bytes.decode(), pub_bytes.decode()


def get_wg_private_public_psk_pair():
    """Pure-Python X25519 keypair + random preshared key, in WireGuard's own
    wire format (32 raw bytes, standard base64 with padding - NOT the
    urlsafe/unpadded encoding generate_x25519_keys() below uses for reality
    keys). Used to be `wg genkey`/`pubkey`/`genpsk` subprocess calls, but
    the `wireguard` package (which provides that CLI) is only installed
    when wireguard_enable is explicitly turned on - since it's off by
    default now, every new user's key generation (called unconditionally
    on insert) would otherwise silently fail. This same format is what
    AmneziaWG's client-facing feature needs too, since awg is
    protocol/key-compatible with wg."""
    import base64
    priv = x25519.X25519PrivateKey.generate()
    pub = priv.public_key()
    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    private_key = base64.b64encode(priv_bytes).decode()
    public_key = base64.b64encode(pub_bytes).decode()
    psk = base64.b64encode(os.urandom(32)).decode()
    return private_key, public_key, psk


def generate_x25519_keys(base_64_encode=True):
    priv = x25519.X25519PrivateKey.generate()
    pub = priv.public_key()
    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    pub_bytes = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    if base_64_encode:
        import base64
        pub_str = base64.urlsafe_b64encode(pub_bytes).decode()[:-1]
        priv_str = base64.urlsafe_b64encode(priv_bytes).decode()[:-1]
    else:
        pub_str=pub_bytes.hex()
        priv_str=priv_bytes.hex()
    return {'private_key': priv_str, 'public_key': pub_str}



def generate_ssh_host_keys():
    # DSA deliberately excluded: OpenSSH removed DSA key support entirely
    # (insecure, deprecated for years), so `ssh-keygen -t dsa` just fails
    # outright on any current OS ("unknown key type dsa"), and nothing
    # downstream ever consumed keys_dict['dsa'] anyway - _v97's own
    # set_hconfig calls for ssh_host_dsa_pk/pub are commented out, same as
    # get_ssh_hostkeys() in hutils/proxy/shared.py.
    key_types = ["ecdsa", "ed25519", "rsa"]
    keys_dict = {}

    # Generate and read keys
    for key_type in key_types:
        key_file = f"ssh_host_{key_type}_key"

        subprocess.run([
            "ssh-keygen", "-t", key_type,
            "-f", key_file,
            "-N", "" 
        ], check=True,stdout=sys.stderr)

        keys_dict[key_type]={}
        with open(key_file, "r") as f:
            keys_dict[key_type]['pk'] = f.read()
        with open(f"{key_file}.pub", "r") as f:
            keys_dict[key_type]['pub'] = f.read()

        os.remove(key_file)
        os.remove(f"{key_file}.pub")  # Remove the public key if not needed
    return keys_dict