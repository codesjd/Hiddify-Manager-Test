mkdir -p /opt/hiddify-manager/acme.sh/www/.well-known/acme-challenge
echo "location /.well-known/acme-challenge {root /opt/hiddify-manager/acme.sh/www/;}" >/opt/hiddify-manager/nginx/parts/acme.conf
chown -R nginx /opt/hiddify-manager/acme.sh/www/

# nginx is already restarted once, up front, by cert_utils.sh's
# start_nginx_acme() (called before the parallel get_cert loop in run.sh) -
# this acme-challenge location is identical for every domain, so there's
# nothing domain-specific to reload here. This pre-hook used to also
# `systemctl restart hiddify-nginx` on every call; with several domains'
# get_cert() running in parallel, each one's restart could race and tear
# down nginx mid-challenge for another domain, failing with "Job for
# hiddify-nginx.service failed" and silently falling back to a self-signed
# cert. Only the directory/permission setup (safe to repeat) stays here.
