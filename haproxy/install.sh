source ../common/utils.sh
rm -rf *.template
if is_installed sniproxy; then
    # systemctl kill hiddify-sniproxy > /dev/null 2>&1
    systemctl stop hiddify-sniproxy >/dev/null 2>&1
    systemctl disable hiddify-sniproxy >/dev/null 2>&1
    pkill -9 sniproxy >/dev/null 2>&1
fi

HAPROXY_VERSION=3.3
if grep -q '^VERSION_CODENAME=jammy' /etc/os-release; then \
    warning "Deprecated Warning: OS is Jammy (Ubuntu 22.04). haproxy max version is 3.0"; \
    HAPROXY_VERSION=3.0
    echo "OS version is 22, checking for haproxy=${HAPROXY_VERSION}"
fi
if ! is_installed_package "haproxy=${HAPROXY_VERSION}"; then
    echo "Adding PPA for haproxy-${HAPROXY_VERSION}"
    # add-apt-repository fetches the PPA's metadata/signing key from
    # Launchpad (ppa.launchpadcontent.net / keyserver.ubuntu.com) with no
    # built-in timeout - when Launchpad is slow or unreachable from a given
    # network (seen repeatedly on Turkey-hosted servers), this call can hang
    # or fail outright, and previously only got a single blind retry with no
    # backoff. Same class of problem the acme.sh timeout in cert_utils.sh's
    # acmecmd() already addresses for cert issuance - bound each attempt and
    # retry with backoff instead of letting one slow/blocked request take
    # down the whole install.
    ppa_added=false
    for backoff in 2 4 8 16; do
        if timeout 90 add-apt-repository -y ppa:vbernat/haproxy-${HAPROXY_VERSION}; then
            ppa_added=true
            break
        fi
        warning "add-apt-repository for haproxy-${HAPROXY_VERSION} failed, retrying in ${backoff}s"
        sleep "$backoff"
    done
    if ! $ppa_added; then
        error "Could not add PPA for haproxy-${HAPROXY_VERSION} after multiple attempts"
    fi
    echo "Installing haproxy ${HAPROXY_VERSION}"
    install_package "haproxy=${HAPROXY_VERSION}.*"
else
    echo "haproxy ${HAPROXY_VERSION} is already installed"
fi
systemctl kill haproxy >/dev/null 2>&1
systemctl stop haproxy >/dev/null 2>&1
systemctl disable haproxy >/dev/null 2>&1

ln -sf $(pwd)/hiddify-haproxy.service /etc/systemd/system/hiddify-haproxy.service
systemctl enable hiddify-haproxy.service
