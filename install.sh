#!/bin/bash
cd $(dirname -- "$0")
source ./common/utils.sh
NAME="0-install"
LOG_FILE="$(log_file $NAME)"
# Fix the installation directory
if [ ! -d "/opt/hiddify-manager/" ] && [ -d "/opt/hiddify-server/" ]; then
    mv /opt/hiddify-server /opt/hiddify-manager
    ln -s /opt/hiddify-manager /opt/hiddify-server
fi
if [ ! -d "/opt/hiddify-manager/" ] && [ -d "/opt/hiddify-config/" ]; then
    mv /opt/hiddify-config/ /opt/hiddify-manager/
    ln -s /opt/hiddify-manager /opt/hiddify-config
fi

export DEBIAN_FRONTEND=noninteractive
if [ "$(id -u)" -ne 0 ]; then
    echo 'This script must be run by root' >&2
    exit 1
fi
function main() {
    update_progress "Please wait..." "We are going to install Hiddify..." 0
    export ERROR=0
    
    export PROGRESS_ACTION="Installing..."
    if [ "$MODE" == "apply_users" ];then
        export DO_NOT_INSTALL="true"
    elif [ -d "/hiddify-data-default/" ] && [ -z "$(ls -A /hiddify-data/ 2>/dev/null)" ]; then
        cp -r /hiddify-data-default/* /hiddify-data/
    fi
    if [ "$DO_NOT_INSTALL" == "true" ];then
        PROGRESS_ACTION="Applying..."
    fi

    export USE_VENV=313

    install_python
    activate_python_venv
    
    if [ "$MODE" != "apply_users" ]; then
        clean_files
        update_progress "${PROGRESS_ACTION}" "Common Tools and Requirements" 2
        runsh install.sh common &
        if [ "$MODE" != "docker" ];then
            install_run other/redis &
            # DB_BACKEND defaults to mysql (unchanged behavior for every
            # existing install). Set DB_BACKEND=postgres or
            # DB_BACKEND=timescaledb before running install.sh to opt into
            # the new backend instead - e.g.:
            #   DB_BACKEND=timescaledb ./install.sh --no-gui
            export DB_BACKEND="${DB_BACKEND:-mysql}"
            if [ "$DB_BACKEND" == "postgres" ] || [ "$DB_BACKEND" == "timescaledb" ]; then
                install_run other/postgres &
            else
                install_run other/mysql &
            fi
        fi    
        wait
        # Because we need to generate reality pair in panel
        # is_installed xray || bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install --version 1.8.4
        
        install_run hiddify-panel
    fi
    
    # source common/set_config_from_hpanel.sh
    if [ "$DO_NOT_RUN" != "true" ];then
      update_progress "HiddifyPanel" "Reading Configs from Panel..." 5
      set_config_from_hpanel

      update_progress "Applying Configs" "..." 8

      bash common/replace_variables.sh
    fi
    
    if [ "$MODE" != "apply_users" ]; then
        bash ./other/deprecated/remove_deprecated.sh
        update_progress "Configuring..." "System and Firewall settings" 10
        runsh run.sh common &
        
        update_progress "${PROGRESS_ACTION}" "Nginx" 15
        install_run nginx &
        
        (
            update_progress "${PROGRESS_ACTION}" "Haproxy for Spliting Traffic" 20
            install_run haproxy
        
            update_progress "${PROGRESS_ACTION}" "Getting Certificates" 30
            install_run acme.sh 
        )&
        
        update_progress "${PROGRESS_ACTION}" "dnstt Proxy" 40
        install_run other/dnstt $(hconfig "dnstt_enable") &

        update_progress "${PROGRESS_ACTION}" "Telegram Proxy" 40
        install_run other/telegram $(hconfig "telegram_enable") &
        
        update_progress "${PROGRESS_ACTION}" "FakeTlS Proxy" 45
        install_run other/ssfaketls $(hconfig "ssfaketls_enable") &
        
        # update_progress "${PROGRESS_ACTION}" "V2ray WS Proxy" 50
        # install_run other/v2ray $ENABLE_V2RAY
        
        update_progress "${PROGRESS_ACTION}" "SSH Proxy" 55
        install_run other/ssh 0 &
        
        #update_progress "${PROGRESS_ACTION}" "ShadowTLS" 60
        #install_run other/shadowtls $(hconfig "shadowtls_enable")
        
        update_progress "${PROGRESS_ACTION}" "Warp" 70
        
        if [[ $(hconfig "warp_mode") != "disable" ]];then
            install_run other/warp 1 &
        else   
            install_run other/warp 0 &
        fi

        # core_type only decides the PRIMARY core. The two cores are
        # complementary, not redundant: xray serves vless/vmess/trojan/reality,
        # while hysteria2/tuic/shadowsocks2022/anytls/mieru/naive exist ONLY as
        # singbox inbounds (there is no xray/configs/ template for them). So on
        # an xray-core install singbox must ALSO run, or every one of those
        # protocols points at a dead port. They don't collide: singbox's
        # overlapping inbounds (vless/vmess/trojan/reality) self-exclude via
        # `{% if core_type=="singbox" %}` gates, and the two cores use distinct
        # control/socks ports (xray 10085/1234, singbox 10086/2000). The panel
        # also polls singbox on 10086 for usage stats, so it must be up.
        # Only the SINGBOX-primary case can safely drop xray (xhttp is the sole
        # xray-only transport and is already filtered from singbox subs).
        CORE_TYPE=$(hconfig "core_type")
        XRAY_ENABLE=0
        SINGBOX_ENABLE=0
        
        # ponytail: gate xray strictly on xhttp usage (config or domain). fallback to True on error so broken check doesn't kill live domain.
        # NOTE: create_app_wsgi() (not create_app) reads sys.argv[1]
        # unconditionally to decide cli-vs-web mode - it IndexErrors under
        # `python3 -c "..."` (argv is just ['-c'], no [1]), which was
        # silently swallowed by 2>/dev/null here, meaning this check has
        # been falling through to the "True" fallback on every single run
        # since it shipped, never actually querying the DB. Fixed by using
        # create_app(app_mode="cli") directly instead of the wsgi-argv-
        # sniffing wrapper.
        HAS_XHTTP_DOMAIN=$(python3 -c "from hiddifypanel.base import create_app; app=create_app(app_mode='cli'); app.app_context().push(); from hiddifypanel.models import Domain, DomainType; print('True' if Domain.query.filter(Domain.mode==DomainType.special_reality_xhttp).first() else 'False')" 2>/dev/null || echo "True")

        # core_type_auto (fresh installs only - see init_db.py) re-resolves
        # core_type from actual xhttp usage on every apply: no xhttp -> the
        # lighter singbox-only path, xhttp in use -> xray. Persisted back to
        # the DB (not just a local variable) because Jinja config generation
        # later in this same run reads core_type straight from the DB too.
        # Admins who ever explicitly pick a value via Settings flip
        # core_type_auto off (SettingAdmin.py), so this never overwrites a
        # deliberate choice - only ever touches an install that has never
        # had one made.
        if [[ "$(hconfig "core_type_auto")" == "True" ]]; then
            if [[ "$(hconfig "xhttp_enable")" == "True" ]] || [[ "$HAS_XHTTP_DOMAIN" == "True" ]]; then
                RESOLVED_CORE_TYPE="xray"
            else
                RESOLVED_CORE_TYPE="singbox"
            fi
            if [[ "$RESOLVED_CORE_TYPE" != "$CORE_TYPE" ]]; then
                if python3 -c "from hiddifypanel.base import create_app; from hiddifypanel.models import ConfigEnum, set_hconfig; app=create_app(app_mode='cli'); app.app_context().push(); set_hconfig(ConfigEnum.core_type, '$RESOLVED_CORE_TYPE')" 2>/dev/null; then
                    CORE_TYPE="$RESOLVED_CORE_TYPE"
                else
                    warning "core_type auto-resolution failed to persist - keeping previous value ($CORE_TYPE) for this run."
                fi
            fi
        fi

        if [[ "$CORE_TYPE" == "xray" ]] || [[ "$(hconfig "xhttp_enable")" == "True" ]] || [[ "$HAS_XHTTP_DOMAIN" == "True" ]]; then
            XRAY_ENABLE=1
        fi
        
        if [[ "$CORE_TYPE" == "singbox" ]]; then
            SINGBOX_ENABLE=1
        fi
        for f in hysteria_enable tuic_enable anytls_enable shadowsocks2022_enable naive_enable mieru_enable; do
            [[ "$(hconfig "$f")" == "True" ]] && SINGBOX_ENABLE=1
        done

        update_progress "${PROGRESS_ACTION}" "Xray" 75
        
        install_run xray $XRAY_ENABLE &
        
        
        update_progress "${PROGRESS_ACTION}" "HiddifyCli" 80
        install_run other/hiddify-cli $(hconfig "hiddifycli_enable") &

        # L2TP/IPsec (strongSwan+xl2tpd). Deliberately inside the
        # non-apply_users block, unlike wireguard/amneziawg below: its
        # per-user credentials (chap-secrets) refresh on a full Apply
        # Configs, not on the per-user fast-path - restarting strongswan/
        # xl2tpd on every user add would drop every live tunnel, and
        # jinja.py doesn't re-render other/l2tp on apply_users anyway.
        # has_l2tp_outbound (not the raw l2tp_enable inbound toggle) so an
        # L2TP outbound chaining row also brings the daemons up even when
        # inbound l2tp_enable is off - same reasoning as has_amneziawg_outbound
        # below.
        update_progress "${PROGRESS_ACTION}" "L2TP/IPsec" 82
        install_run other/l2tp $(hconfig "has_l2tp_outbound") &

    fi


    update_progress "${PROGRESS_ACTION}" "Wireguard" 85
    install_run other/wireguard $(hconfig "wireguard_enable") &

    update_progress "${PROGRESS_ACTION}" "AmneziaWG" 90
    install_run other/amneziawg $(hconfig "has_amneziawg_outbound") &

    update_progress "${PROGRESS_ACTION}" "Singbox" 95
    install_run singbox ${SINGBOX_ENABLE:-1} &
    
    update_progress "${PROGRESS_ACTION}" "Almost Finished" 98
    wait 
    echo "---------------------Finished!------------------------"
    remove_lock $NAME
    if [ "$MODE" != "apply_users" ]; then
        # --kill-who=main: `systemctl kill` (unlike `restart`/`stop`) ignores
        # the unit's KillMode= entirely and defaults to --kill-who=all, i.e.
        # every process in hiddify-panel.service's cgroup. When this install
        # run itself was launched from the panel (commander()'s detached
        # child, see run_commander.py), install.sh IS one of those
        # processes - so the bare form here was killing this very script
        # mid-run, well before it ever reached the rest of the install
        # steps. Restrict the kill to the tracked main PID only.
        systemctl kill -s SIGTERM --kill-who=main hiddify-panel
    fi
    systemctl start hiddify-panel
    update_progress "${PROGRESS_ACTION}" "Done" 100
    
}

function clean_files() {
    rm -rf log/system/xray*
    rm -rf /opt/hiddify-manager/xray/configs/*.json
    rm -rf /opt/hiddify-manager/singbox/configs/*.json
    rm -rf /opt/hiddify-manager/haproxy/*.cfg
    find ./ -type f -name "*.template" -exec rm -f {} \;
}

function cleanup() {
    error "Script interrupted. Exiting..."
    # disable_ansii_modes
    remove_lock $NAME
    exit 9
}

# Trap the Ctrl+C signal and call the cleanup function
trap cleanup SIGINT

function set_config_from_hpanel() {
    reload_all_configs >/dev/null
    if [[ $? != 0 ]]; then
        error "Exception in Hiddify Panel. Please send the log to hiddify@gmail.com"
        exit 4
    fi
    
    export SERVER_IP=$(curl --connect-timeout 1 -s https://v4.ident.me/)
    export SERVER_IPv6=$(curl --connect-timeout 1 -s https://v6.ident.me/)
}

function install_run() {
    # HIDDIFY_APPLY_SUBSYSTEMS, when set, scopes a "Apply Configs" run
    # (DO_NOT_INSTALL=true) to only the listed subsystems - e.g. changing
    # just core_type shouldn't also re-run acme.sh's cert issuance, restart
    # telegram/dnstt/speedtest, etc. Only ever takes effect for the apply
    # path: a real install/reinstall (DO_NOT_INSTALL unset) always touches
    # everything, ignoring any stale value here, and an unset/empty
    # HIDDIFY_APPLY_SUBSYSTEMS (every caller before this feature existed,
    # and any caller that doesn't explicitly opt in) runs every subsystem
    # exactly as before - this is a strictly additive, opt-in narrowing.
    if [ "$DO_NOT_INSTALL" == "true" ] && [ -n "$HIDDIFY_APPLY_SUBSYSTEMS" ] && [ "$1" != "hiddify-panel" ]; then
        # hiddify-panel itself is exempt - its run.sh runs DB migrations
        # (hiddify-panel-cli init-db) and restarts the panel/background-tasks
        # services, none of which are optional per-subsystem work the way
        # xray/haproxy/acme.sh/etc are. It had no enable-flag gate before
        # this feature either (always ran unconditionally), so it keeps
        # doing exactly that regardless of what's in the subsystems list.
        case ",$HIDDIFY_APPLY_SUBSYSTEMS," in
            *",$1,"*) ;;
            *)
                echo "======================$1==(skipped, not in HIDDIFY_APPLY_SUBSYSTEMS)========={"
                echo "}========================$1==================================="
                return 0
                ;;
        esac
    fi
    echo "======================$1====================================={"
   if [ "$DO_NOT_INSTALL" != "true" ];then
        # ponytail: gate install.sh on subsystem enable flag (last arg)
        # when the flag is 0/false/False, skip package installation entirely
        # but still run run.sh so the subsystem is stopped/cleaned up
        _ENABLED=true
        _LAST_ARG="${@: -1}"
        case "$_LAST_ARG" in
            0|false|False|"") _ENABLED=false ;;
        esac
        if [ "$_ENABLED" == "true" ]; then
            runsh install.sh $@
            if [ "$MODE" != "apply_users" ] && [ "$MODE" != "docker"  ]; then
                systemctl daemon-reload
            fi
        fi
    fi
    if [ "$DO_NOT_RUN" != "true" ];then
         runsh run.sh $@
    fi
    echo "}========================$1==================================="
}

function runsh() {
    command=$1
    if [[ $3 == "false" || $3 == "0" ]]; then
        command=disable.sh
    fi
    pushd $2 >>/dev/null
    # if [[ $? != 0]];then
    #         echo "$2 not found"
    # fi
    if [[ $? == 0 && -f $command ]]; then
        
        echo "===$command $2"
        bash $command
    fi
    popd >>/dev/null
}

if [[ " $@ " == *" --no-gui "* ]]; then
    set -- "${@/--no-gui/}"
    export MODE="$1"
    set_lock $NAME
    if [[ " $@ " == *" --no-log "* ]]; then
        set -- "${@/--no-log/}"
        main
    else
        main |& tee $LOG_FILE
    fi
    error_code=$?
    remove_lock $NAME
else
    show_progress_window --subtitle $(get_installed_config_version) --log $LOG_FILE ./install.sh $@ --no-gui --no-log
    error_code=$?
    if [[ $error_code != "0" ]]; then
        # echo less -r -P"Installation Failed! Press q to exit" +G "$log_file"
        msg_with_hiddify "Installation Failed! $error_code"
    else
        msg_with_hiddify "The installation has successfully completed."
        check_hiddify_panel $@ |& tee -a $LOG_FILE
    fi
fi

exit $error_code
