source /opt/hiddify-manager/common/utils.sh

install_package shadowsocks-libev

# simple-obfs (provides obfs-server, what hiddify-ss-faketls.service
# actually execs) is a long-unmaintained upstream package that newer
# Ubuntu releases have started dropping from their archives entirely
# ("no installation candidate", confirmed on Ubuntu 26.04) - not just an
# old-version problem like nginx's pin, there is no apt version of it
# available at all anymore on those releases. Try apt first since it's
# faster and still fine on any release that still carries it, and only
# build from source (upstream's own documented build steps) as a
# fallback when apt has nothing to offer.
if ! command -v obfs-server >/dev/null 2>&1; then
    install_package simple-obfs
fi
if ! command -v obfs-server >/dev/null 2>&1; then
    echo "simple-obfs has no apt package on this OS - building obfs-server from source"
    install_package build-essential autoconf libtool libssl-dev libpcre3-dev libev-dev automake asciidoc xmlto git
    build_dir=$(mktemp -d)
    if git clone --depth 1 https://github.com/shadowsocks/simple-obfs.git "$build_dir/simple-obfs" \
        && (
            cd "$build_dir/simple-obfs" \
            && git submodule update --init --recursive --depth 1 \
            && ./autogen.sh \
            && ./configure \
            && make -j"$(nproc)" \
            && make install
        )
    then
        echo "obfs-server built and installed successfully"
    else
        error "Building simple-obfs from source failed - ss-faketls (Shadowsocks fake-TLS) will not be available on this install"
    fi
    rm -rf "$build_dir"
fi

chmod 600 *.service*
ln -sf $(pwd)/hiddify-ss-faketls.service /etc/systemd/system/hiddify-ss-faketls.service
systemctl disable --now ss-faketls.service > /dev/null 2>&1
rm ss-faketls.service* > /dev/null 2>&1