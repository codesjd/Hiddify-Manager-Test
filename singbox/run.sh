source /opt/hiddify-manager/common/utils.sh
ln -sf $(pwd)/hiddify-singbox.service /etc/systemd/system/hiddify-singbox.service
systemctl enable hiddify-singbox.service

set_files_in_folder_readable_to_hiddify_common_group configs/01_api.json

# curl -s -x socks://127.0.0.1:3000 http://ip-api.com?fields=message,country,countryCode,city,isp,org,as,query

# There used to be a `sing-box check -C configs` pre-flight gate here, but
# the actual binary was renamed to hiddify-core (see install.sh's `ln -sf
# .../hiddify-core /usr/bin/hiddify-core`) with no `sing-box` command ever
# installed - this call has always failed with "command not found" (exit
# 127), so this branch silently took the `else` below on every single
# install/apply, never once reaching reload/start. hiddify-core's CLI has
# no equivalent "validate this merged multi-file config directory" command
# (`parse` only accepts one complete, self-contained config file, not the
# fragment-per-file directory srun -C merges at runtime) to replace it
# with, so just start the service directly - an actually-invalid config
# still surfaces clearly via `systemctl status`/journalctl and the
# service's own Restart=always/RestartSec=5 crash-loop, instead of the
# service silently never starting at all regardless of whether the config
# was valid.
systemctl reload hiddify-singbox.service
systemctl start hiddify-singbox.service
