source /opt/hiddify-manager/common/utils.sh

# sing-box has no native AmneziaWG support (verified against hiddify-sing-box's
# source directly - no Jc/Jmin/Jmax/amnezia anywhere in it), so this runs as
# its own standalone WireGuard-family interface, the same way WARP runs its
# own wg-quick@warp interface via other/warp/wireguard/. sing-box's outbound
# just binds to whatever interface this brings up (bind_interface), same
# mechanism as WARP - no core-level protocol support needed.
#
# Two upstream projects, neither ships prebuilt Linux binaries as of writing,
# so both are built from source here:
#   - amneziawg-tools: C, provides `awg`/`awg-quick` (forks of wg/wg-quick)
#     and an awg-quick@.service systemd template.
#   - amneziawg-go: Go, userspace WireGuard-family implementation. awg-quick
#     tries `ip link add type amneziawg` (a kernel module essentially no
#     stock cloud kernel has) first and automatically falls back to
#     amneziawg-go in PATH if that fails - so no kernel module/DKMS build is
#     needed, just this binary.
#
# NOTE: untested. I don't have a real server to build/run either of these
# on, so this is written directly from both projects' own build
# instructions/source, not verified end-to-end. Please report the exact
# output if `bash install.sh` fails here.

install_package golang-go

BUILD_DIR="$(pwd)/build"
mkdir -p "$BUILD_DIR"

if ! command -v awg-quick >/dev/null 2>&1; then
    rm -rf "$BUILD_DIR/amneziawg-tools"
    git clone --depth 1 https://github.com/amnezia-vpn/amneziawg-tools "$BUILD_DIR/amneziawg-tools" || exit 1
    (cd "$BUILD_DIR/amneziawg-tools/src" && make && make install WITH_SYSTEMDUNITS=yes) || exit 2
fi

if ! command -v amneziawg-go >/dev/null 2>&1; then
    rm -rf "$BUILD_DIR/amneziawg-go"
    git clone --depth 1 https://github.com/amnezia-vpn/amneziawg-go "$BUILD_DIR/amneziawg-go" || exit 3
    (cd "$BUILD_DIR/amneziawg-go" && make) || exit 4
    install -m 755 "$BUILD_DIR/amneziawg-go/amneziawg-go" /usr/bin/amneziawg-go || exit 5
fi

mkdir -p /etc/amnezia/amneziawg
