source ../common/utils.sh
# Not pinned to a specific nginx version: nginx.org's own apt repo only
# ever publishes the current stable/mainline builds for each Ubuntu
# codename, not every old version forever - a hardcoded pin like
# "nginx=1.26.*" silently stops matching anything the moment nginx.org
# moves that codename's repo on to a newer line (e.g. a brand new Ubuntu
# release that only ever had 1.30.x published for it), and install_package
# doesn't treat that as fatal, so the whole install would otherwise sail
# on with nginx never actually installed. Taking whatever's current for
# the host's own codename avoids needing to keep bumping this by hand.
if ! is_installed "nginx"; then
    useradd nginx
    curl https://nginx.org/keys/nginx_signing.key | gpg --dearmor |
        sudo tee /usr/share/keyrings/nginx-archive-keyring.gpg >/dev/null
    echo "deb [signed-by=/usr/share/keyrings/nginx-archive-keyring.gpg] \
    http://nginx.org/packages/ubuntu $(lsb_release -cs) nginx" |
        sudo tee /etc/apt/sources.list.d/nginx.list
    sudo apt update -y

fi
install_package "nginx"

systemctl kill nginx >/dev/null 2>&1
systemctl disable nginx >/dev/null 2>&1
systemctl kill apache2 >/dev/null 2>&1
systemctl disable apache2 >/dev/null 2>&1
# pkill -9 nginx

rm /etc/nginx/conf.d/web.conf >/dev/null 2>&1
rm /etc/nginx/sites-available/default >/dev/null 2>&1
rm /etc/nginx/sites-enabled/default >/dev/null 2>&1
rm /etc/nginx/conf.d/default.conf >/dev/null 2>&1
rm /etc/nginx/conf.d/xray-base.conf >/dev/null 2>&1
rm /etc/nginx/conf.d/speedtest.conf >/dev/null 2>&1

mkdir -p run
ln -sf $(pwd)/hiddify-nginx.service /etc/systemd/system/hiddify-nginx.service
systemctl enable hiddify-nginx.service
