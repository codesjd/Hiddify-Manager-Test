import glob
from typing import List, Literal, Set, Union
from urllib.parse import urlparse

from dns.rdtypes.svcbbase import ECHParam

import urllib.request
import ipaddress
from hiddifypanel.hutils.network.auto_ip_selector import IPASN
import requests
import random
import socket
import threading
import time
import ssl
import re
import os
import ipaddress
import psutil
import socket
import threading
from typing import List, Union, Literal

from hiddifypanel.models import *
from hiddifypanel.cache import cache

import dns.resolver
import base64


def get_domain_ip_old(domain: str, retry: int = 3, version: Literal[4, 6] | None = None) -> Union[ipaddress.IPv4Address, ipaddress.IPv6Address, None]:
    res = None
    if not version:
        try:
            res = socket.gethostbyname(domain)
        except BaseException:
            pass

    if not res and version != 6:
        try:
            res = socket.getaddrinfo(domain, None, socket.AF_INET)[0][4][0]
        except BaseException:
            pass

    if not res and version != 4:
        try:
            res = f"{socket.getaddrinfo(domain, None, socket.AF_INET6)[0][4][0]}"

        except BaseException:
            pass

    if retry > 0:
        return get_domain_ip_old(domain, retry=retry - 1, version=version)

    if not res:
        return None
    return ipaddress.ip_address(res)


def get_domain_ip(domain: str, retry: int = 3, version: Literal[4, 6] | None = None) -> Union[ipaddress.IPv4Address, ipaddress.IPv6Address, None]:
    ips=get_domain_ips_cached(domain)
    ips=[ip for ip in ips if version==None or (version==4 and isinstance(ip,ipaddress.IPv4Address)) or  (version==6 and isinstance(ip,ipaddress.IPv6Address)) ]
    if ips:
        return random.sample(ips,1)[0]
    return get_domain_ip_old(domain,0)

_pinned_cert_cache: dict = {}
_pinned_cert_inflight: set = set()


def _fetch_cert_sha256_blocking(host: str, port: int, timeout: float) -> Union[str, None]:
    import hashlib
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls_sock:
                der_cert = tls_sock.getpeercert(binary_form=True)
        if not der_cert:
            return None
        digest = hashlib.sha256(der_cert).digest()
        # Xray-core's pinnedPeerCertSha256 expects the digest as hex, NOT
        # base64 - a base64-encoded value here (e.g. "wav+cIVA...") made
        # every config using it fail with "encoding/hex: invalid byte" as
        # soon as the base64 alphabet produced a character hex doesn't have.
        return digest.hex()
    except Exception:
        return None


def _background_fetch_cert(host: str, port: int, key: str):
    import time
    try:
        result = _fetch_cert_sha256_blocking(host, port, timeout=2.0)
        if result:
            _pinned_cert_cache[key] = (result, time.time())
    finally:
        _pinned_cert_inflight.discard(key)


def get_pinned_cert_sha256(host: str, port: int = 443) -> Union[str, None]:
    """Non-blocking. Returns a cached SHA256 pin (hex, in the form
    Xray-core's pinnedPeerCertSha256 expects) for host:port if we already
    fetched one recently, or None otherwise - NEVER does network I/O on the
    calling thread. On a cache miss this kicks off a background thread to
    populate the cache for next time, but always returns immediately.

    This matters because this gets called from the live subscription-
    generation request path (get_valid_proxies -> make_proxy, on every
    domain with allow_insecure=True) - an earlier version did a real TLS
    handshake inline here with up to a 3s timeout, which could stack up
    across several domains and blow past upstream request timeouts,
    surfacing as 500s when loading a subscription. Callers already treat
    None as "not available yet, fall back to allowInsecure" so returning
    None immediately on a cold cache is always safe, just less precise
    until the background fetch finishes (usually within a few seconds).
    """
    import time
    key = f"{host}:{port}"
    cached = _pinned_cert_cache.get(key)
    # A 1-hour TTL with no invalidation hook meant a pin fetched before a
    # domain's cert finished issuing (e.g. right after the domain is added,
    # hitting whatever cert HAProxy defaults to for an unmatched SNI) kept
    # being served as fact for up to an hour after the real cert appeared -
    # every hysteria2/tuic/anytls/naive-quic connection pinned to that host
    # would fail with a cert mismatch the whole time. 300s (matching
    # get_domain_ips_cached's TTL below) bounds that staleness window to
    # minutes instead of up to an hour.
    if cached and (time.time() - cached[1]) < 300:
        return cached[0]
    if key not in _pinned_cert_inflight:
        _pinned_cert_inflight.add(key)
        threading.Thread(target=_background_fetch_cert, args=(host, port, key), daemon=True).start()
    return None


def invalidate_pinned_cert_cache(host: str, port: int = 443):
    """Drop a cached pin so the next get_pinned_cert_sha256() call re-fetches
    it instead of serving a stale value for up to 300s. Call this whenever a
    domain's cert is known to have just changed (added/edited domain, cert
    reissue) so the very next subscription request already reflects it."""
    _pinned_cert_cache.pop(f"{host}:{port}", None)



@cache.cache(300)
def _get_domain_ips_cached_raw(domain: str, retry: int = 0) -> Set[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    try:
        return set(ipaddress.ip_address(domain))
    except:
        return get_domain_ips(domain,retry)


_failed_dns_lookup_at: dict = {}
# Bounds how often a domain that never resolves (e.g. resolve_ip enabled on a
# domain with no real DNS record) can trigger a full synchronous DNS
# resolution. Without this, every call for such a domain did a fresh,
# multi-second lookup (see the invalidate-on-empty-result path below) with no
# floor at all - sni_host_server_extractor() calls get_domain_ips_cached()
# once per proxy per domain, so a single broken domain turned every
# subscription/config page load into dozens of consecutive multi-second DNS
# resolutions, hanging the request for minutes.
_FAILED_DNS_LOOKUP_RETRY_SECONDS = 10


# retry=0 here (unlike get_domain_ips's own retry=3 default): get_domain_ips
# recurses once per unit of retry with no delay/backoff between attempts, so
# retrying a domain that has no DNS record just repeats the identical failing
# query several times over. That's harmless for the one-off manual
# get_domain_ips() calls (e.g. the admin "test DNS" action), but this cached
# entry point is what get_valid_proxies()/DomainAdmin's domain list call once
# per domain in a plain loop - multiplying each domain's cost by the retry
# count turns a handful of stale domains into a multi-minute page load.
def get_domain_ips_cached(domain: str, retry: int = 0) -> Set[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    result = _get_domain_ips_cached_raw(domain, retry)
    if not result:
        last_failure = _failed_dns_lookup_at.get(domain)
        if last_failure is None:
            # First time this domain has ever come back empty - the lookup
            # we just did was already fresh (a cold cache miss), so redoing
            # it now would just repeat the same dead query. Record the
            # failure and return; a retry only makes sense once some time
            # has passed (handled below).
            _failed_dns_lookup_at[domain] = time.time()
            return result
        if (time.time() - last_failure) < _FAILED_DNS_LOOKUP_RETRY_SECONDS:
            return result
        # A failed lookup is exactly the case where a 300s cache actively
        # hurts - e.g. an admin adds a domain before its DNS record
        # exists, gets a validation error, fixes DNS, and retries within
        # the window - only to have the same stale "can't resolve"
        # served back instead of a fresh lookup. Unlike a real answer,
        # an empty result isn't expensive information worth preserving,
        # so don't trust/serve it from cache - invalidate and try once
        # more for real, but no more than once every
        # _FAILED_DNS_LOOKUP_RETRY_SECONDS for the same domain.
        _get_domain_ips_cached_raw.invalidate(domain, retry)
        result = get_domain_ips(domain, retry)
        if not result:
            _failed_dns_lookup_at[domain] = time.time()
        else:
            _failed_dns_lookup_at.pop(domain, None)
    return result

def get_domain_ips(domain: str, retry: int = 3) -> Set[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    res = set()
    if retry < 0:
        return res
    try:
        _, _, ips = socket.gethostbyname_ex(domain)
        for ip in ips:
            res.add(ipaddress.ip_address(ip))
    except Exception:
        pass

    try:
        for ip in socket.getaddrinfo(domain, None, socket.AF_INET):
            res.add(ipaddress.ip_address(ip[4][0]))
    except BaseException:
        pass

    try:
        for ip in socket.getaddrinfo(domain, None, socket.AF_INET6):
            res.add(ipaddress.ip_address(ip[4][0]))
    except BaseException:
        pass

    return res or get_domain_ips(domain, retry=retry - 1)


def get_socket_public_ip(version: Literal[4, 6]) -> Union[ipaddress.IPv4Address, ipaddress.IPv6Address, None]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if version == 6:
            s.connect(("2001:4860:4860::8888", 80))
        else:
            s.connect(("8.8.8.8", 80))
        ip_address = ipaddress.ip_address(s.getsockname()[0])
        s.close()
        return ip_address if ip_address.is_global else None
    except socket.error:
        return None



def get_interface_public_ip(version: Literal[4, 6]) -> List[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    addresses = []
    try:
        interfaces = psutil.net_if_addrs()
        for interface_addresses in interfaces.values():
            for addr in interface_addresses:
                if version == 4 and addr.family == socket.AF_INET:
                    ip = addr.address
                elif version == 6 and addr.family == socket.AF_INET6:
                    ip = addr.address
                else:
                    continue

                try:
                    ip_obj = ipaddress.ip_address(ip.split('%')[0])  # Remove scope_id for IPv6
                    if ip_obj.is_global:
                        addresses.append(ip_obj)
                except ValueError:
                    continue

        return addresses

    except (OSError, KeyError):
        return []

@cache.cache(ttl=600)
def get_ips(version: Literal[4, 6] | None = None) -> List[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    if not version:
        return [*get_ips(4), *get_ips(6)]
    addrs = []

    i_ips = get_interface_public_ip(version)
    if i_ips:
        addrs = i_ips

    s_ip = get_socket_public_ip(version)
    if s_ip:
        addrs.append(s_ip)

    # send request
    try:
        ip = urllib.request.urlopen(f'https://v{version}.ident.me/',timeout=2).read().decode('utf8')
        if ip:
            addrs.append(ipaddress.ip_address(ip))
    except BaseException:
        pass

    # remove duplicates
    return list(set(addrs))


@cache.cache(ttl=600)
def get_ip_str(version: Literal[4, 6], retry: int = 5) -> str | None:
    ip = get_ip(version, retry)
    if ip is None:
        return None
    return str(ip)


@cache.cache(ttl=600)
def get_ip(version: Literal[4, 6], retry: int = 5) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    ips = get_interface_public_ip(version)
    ip = None
    if ips:
        ip = random.sample(ips, 1)[0]

    if ip is None:
        ip = get_socket_public_ip(version)

    if ip is None:
        try:
            ip = urllib.request.urlopen(f'https://v{version}.ident.me/').read().decode('utf8')
            if ip:
                ip = ipaddress.ip_address(ip)
        except BaseException:
            pass
    if ip is None and retry > 0:
        ip = get_ip(version, retry=retry - 1)
    return ip


def get_random_user_agent():
    
    uas = requests.get('https://cdn.jsdelivr.net/gh/microlinkhq/top-user-agents@master/src/index.json').json()
    if uas:
        return random.sample(uas,1)[0]
    return 
def get_random_domains(count: int = 1, retry: int = 6) -> List[str]:
    try:
        region="CN" if retry<3 else "IR"
        irurl = f"https://api.ooni.io/api/v1/measurements?probe_cc={region}&test_name=web_connectivity&anomaly=false&confirmed=false&failure=false&limit=100&offset={(3-retry%3)*100}"
        # cnurl="https://api.ooni.io/api/v1/measurements?probe_cc=CN&test_name=web_connectivity&anomaly=false&confirmed=false&failure=false&order_by=test_start_time&limit=1000"
        data_ir = requests.get(irurl).json()
        # data_cn=requests.get(url).json()

        domains = [urlparse(d['input']).netloc.lower() for d in data_ir.get('results',{}) if d.get('scores',{}).get('blocking_country') == 0.0]
        domains = [d for d in domains if not d.endswith(".ir") and ".gov" not in d]

        return random.sample(domains, count)
    except BaseException as e:
        print('Error, getting random domains... ', e, 'retrying...', retry)
        if retry <= 0:
            defdomains = ["fa.wikipedia.org",'en.wikipedia.org','wikipedia.org','yahoo.com','en.yahoo.com',"msn.com",'foot.com',"fast.com","speedtest.net","remove.bg","flightradar24.com","chess.com","supercell.com","react.dev","amazon.com","google.com","gstatic.com","mirror.nyist.edu.cn","mirror.nju.edu.cn","hcaptcha.com","sourceforge.net","github.com","www.google.com","hatgpt.com","google.com","github.com","claude.ai","dash.cloudflare.com","pages.dev","workers.dev","gemini.google.com","www.workspace.google.com","www.mail.google.com","www.gstatic.com","www.gmail.com","workspace.google.com","ss1.gstatic.com","mail.google.com","gstatic.com","gmail.com","g3.gstatic.com","g1.gstatic.com","fonts.gstatic.com","csi.gstatic.com","connectivitycheck.gstatic.com","clientservices.googleapis.com","checkin.gstatic.com","beacons.gvt2.com","beacons.gcp.gvt2.com","dash.cloudflare.com","cloudflare.com"]
            print('Error, using default domains')
            return random.sample(defdomains, count)
        return get_random_domains(count, retry - 1)


# not used
def is_domain_support_tls_13(domain: str) -> bool:
    context = ssl.create_default_context()
    port = 433
    with socket.create_connection((domain, port)) as sock:
        with context.wrap_socket(sock, server_hostname=domain) as ssock:
            return ssock.version() == "TLSv1.3"


def is_domain_support_h2_tls13(sni: str, server: str = '') -> bool:
    try:

        context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        context.options |= (ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1)
        context.options |= ssl.OP_NO_COMPRESSION
        context.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20")
        context.set_alpn_protocols(["h2"])
        start_time = time.monotonic()
        with socket.create_connection((server or sni, 443), timeout=2) as sock:

            with context.wrap_socket(sock, server_hostname=sni) as ssock:
                elapsed_time = time.monotonic() - start_time
                valid = ssock.version() == "TLSv1.3"
                if valid:
                    if int(max(1, elapsed_time * 1000)):
                        return True
                return False
    except Exception as e:
        print(f'{sni} {e}')
        return False


def is_domain_reality_friendly(domain: str) -> bool:
    return is_domain_support_h2_tls13(domain)


def fallback_domain_compatible_with_servernames(fallback_domain: str, servername: str) -> bool:
    return is_domain_support_h2_tls13(servername, fallback_domain)


def get_random_decoy_domain() -> str:
    for _ in range(10):
        domains = get_random_domains(10)
        for d in domains:
            if is_domain_use_letsencrypt(d):
                return d

    return "bbc.com"


def is_domain_use_letsencrypt(domain: str) -> bool:
    """
    This function is used to filter the payment and big companies to
    avoid phishing detection
    """
    try:
        # Create a socket connection to the website
        with socket.create_connection((domain, 443)) as sock:
            context = ssl.create_default_context()
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                certificate = ssock.getpeercert()

        issuer = dict(x[0] for x in certificate.get("issuer", []))

        return issuer['organizationName'] == "Let's Encrypt"
    except BaseException:
        return False


@cache.cache(ttl=300)
def get_direct_host_or_ip(prefer_version: int) -> str:
    from hiddifypanel.models import Domain
    direct = Domain.query.filter(Domain.mode == DomainType.direct, Domain.sub_link_only == False).first()
    if not direct:
        direct = Domain.query.filter(Domain.mode == DomainType.direct).first()
    if direct:
        return direct.domain

    direct = get_ip_str(prefer_version)
    if direct:
        return direct

    return get_ip_str(4 if prefer_version == 6 else 6)


def is_ssh_password_authentication_enabled() -> bool:
    def check_file(file_path: str) -> bool:
        if os.path.isfile(file_path):
            try:
                with open(file_path, 'r') as f:
                    for line in f.readlines():
                        line = line.strip()
                        if line.startswith('#'):
                            continue
                        if re.search(r"^PasswordAuthentication\s+no", line, re.IGNORECASE):
                            return False
            except Exception as e:
                print(e)

        return True

    for config_file in glob.glob("/etc/ssh/sshd*") + glob.glob("/etc/ssh/sshd*/*"):
        if not check_file(config_file):
            return False

    return True


def is_out_of_range_port(port: int) -> bool:
    return port < 1 or port > 65535


def add_number_to_ipv4(ip: str, number: int) -> str:
    return str(ipaddress.IPv4Address(ip) + number)


def add_number_to_ipv6(ip: str, number: int) -> str:
    return str(ipaddress.IPv6Address(ip) + number)


@ cache.cache(600)
def is_in_same_asn(domain_or_ip: str, domain_or_ip_target: str) -> bool:
    '''Returns True if domain is in panel ASN'''
    try:
        ip = domain_or_ip if is_ip(domain_or_ip) else get_domain_ip(domain_or_ip)
        ip_target = domain_or_ip_target if is_ip(domain_or_ip_target) else get_domain_ip(domain_or_ip_target)

        if not ip or not ip_target:
            return False

        ip_asn = get_ip_asn(ip)
        ip_target_asn = get_ip_asn(ip_target)

        if not ip_asn or not ip_target_asn:
            return False

        return ip_asn == ip_target_asn
    except Exception as e:
        print(f"An error occurred: {e}")
        return False

        # hutils.flask.flash(_("domain.reality.asn_issue") +
        #                    f"<br> Server ASN={asn_ipv4.get('autonomous_system_organization','unknown')}<br>{domain}_ASN={asn_dip.get('autonomous_system_organization','unknown')}", "warning")


@ cache.cache(600)
def get_ip_asn(ip: ipaddress.IPv4Address | ipaddress.IPv6Address | str) -> str:
    if not IPASN:
        return __get_ip_asn_api(ip)
    try:
        if asn := IPASN.get(str(ip)):
            return str(asn.get('autonomous_system_organization', ''))
        return ''
    except:
        return ''


def __get_ip_asn_api(ip: ipaddress.IPv4Address | ipaddress.IPv6Address | str) -> str:
    ip = str(ip)
    if not is_ip(ip):
        return ''
    endpoint = f'https://ipapi.co/{ip}/asn/'
    return str(requests.get(endpoint).content)


@ cache.cache(3600)
def is_ip(input: str):
    try:
        _ = ipaddress.ip_address(input)
        return True
    except:
        return False


def resolve_domain_with_api(domain: str) -> str:
    if not domain:
        return ''
    endpoint = f'http://ip-api.com/json/{domain}?fields=query'
    return str(requests.get(endpoint).json().get('query'))




@cache.cache(600)
def get_ech_info(domain):
    try:
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ["1.1.1.1"]  # Cloudflare DNS

        answers = resolver.resolve(domain, "HTTPS")
        for rdata in answers:
            for param in rdata.params.values():
                if isinstance(param, ECHParam):
                    ech_bytes = param.ech
                    return base64.b64encode(ech_bytes).decode()
    except BaseException:
        pass

    return None


def all_public_ports():
        tcp_ports={80:"http",443:"tls"}
        udp_ports={443:"quic",}
        log=[]
        if hconfig(ConfigEnum.wireguard_enable):
            udp_ports[hconfig(ConfigEnum.wireguard_port)]="wireguard"
            
            
        if hconfig(ConfigEnum.shadowsocks2022_enable) and (p:=hconfig(ConfigEnum.shadowsocks2022_port)):
            udp_ports[p]="shadowsocks_2022"
            tcp_ports[p]="shadowsocks_2022"
        if hconfig(ConfigEnum.mieru_enable):
            for p in hconfig(ConfigEnum.mieru_tcp_ports).split(","):
                tcp_ports[p]="mieru"
            for p in hconfig(ConfigEnum.mieru_udp_ports).split(","):
                udp_ports[p]="mieru"
        if hconfig(ConfigEnum.ssh_server_enable):
            tcp_ports[hconfig(ConfigEnum.ssh_server_port)]="ssh"
        
        for d in Domain.query.all():
            udp_ports[d.internal_port_tuic]="tuic"
            udp_ports[d.internal_port_naive]="naive"
            udp_ports[d.internal_port_hysteria2]="hysteria"
            # xdns/xicmp (finalmask) ride mKCP, which is UDP-based, same as
            # every other finalmask/QUIC protocol above.
            udp_ports[d.internal_port_xdns]="xdns"
            udp_ports[d.internal_port_xicmp]="xicmp"
            if d.tls_port:
                tcp_ports[d.tls_port]="tls"
                udp_ports[d.tls_port]="quic"
            if d.http_port:
                tcp_ports[d.http_port]="http"

        def to_int(ports):
            r={}
            for p,v in ports.items():
                try:
                    if ip:=int(p):
                        r[ip]=v
                except:
                    pass
            return {k:v for k,v in sorted(r.items())}
        return {"tcp":to_int(tcp_ports),"udp":to_int(udp_ports)}