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
            # Falls back to whatever was persisted from a previous run
            # (see read_persisted_db_backend in common/utils.sh) before
            # ever defaulting to mysql, so a panel-triggered reinstall
            # doesn't silently switch backend out from under an existing
            # sqlite/postgres install.
            export DB_BACKEND="${DB_BACKEND:-$(read_persisted_db_backend)}"
            export DB_BACKEND="${DB_BACKEND:-mysql}"
            persist_db_backend "$DB_BACKEND"
            if [ "$DB_BACKEND" == "postgres" ] || [ "$DB_BACKEND" == "timescaledb" ]; then
                install_run other/postgres &
            elif [ "$DB_BACKEND" == "sqlite" ]; then
                echo "Using SQLite backend (no daemon started)"
            else
                install_run other/mysql &
            fi
        fi    
        wait
        # Because we need to generate reality pair in panel
        # is_installed xray || bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install --version 1.8.4
        
        install_run hiddify-panel
    fi

    if [ "$MODE" != "apply_users" ]; then
        # core_type_auto (fresh installs only - see init_db.py) re-resolves
        # which core is PRIMARY (not whether it runs - both always run, see
        # the XRAY_ENABLE/SINGBOX_ENABLE comment below) from actual xhttp
        # usage. Persisted back to the DB, and MUST run before
        # set_config_from_hpanel/reload_all_configs (a few lines down) -
        # that call snapshots the current DB config into current.json,
        # which is what Jinja template rendering (replace_variables.sh)
        # reads to decide, at render time, which core's inbound templates
        # actually emit for every core_type=="xray"|"singbox"-gated
        # protocol (vless/vmess/trojan/reality etc). Resolving core_type
        # any later than this left the rendered xray/singbox configs on
        # disk reflecting the OLD core_type while the subscription
        # generator (which reads core_type live, well after this point)
        # already reflected the NEW one - subscriptions advertised
        # whichever core's inbound the *new* value implied, even though
        # the actually-rendered/running config on disk still matched the
        # old one, so those proxies were unreachable. Admins who ever
        # explicitly pick a value via Settings flip core_type_auto off
        # (SettingAdmin.py), so this never overwrites a deliberate choice -
        # only ever touches an install that has never had one made.
        #
        # Reads/writes go straight through the DB via Python, not the bash
        # hconfig() helper - hconfig() reads /opt/hiddify-manager/current.json,
        # which set_config_from_hpanel/reload_all_configs (below) is what
        # (re)generates, and on a genuinely fresh install that file doesn't
        # exist yet at this point in the script. Also uses create_app(app_
        # mode="cli") directly rather than create_app_wsgi(), which reads
        # sys.argv[1] unconditionally to decide cli-vs-web mode and
        # IndexErrors under `python3 -c "..."` (argv is just ['-c'], no [1]).
        #
        # HIDDIFY_CFG_PATH points create_app() at hiddify-panel/app.cfg by
        # absolute path: create_app() loads it relative to CWD by default
        # ('app.cfg', see base.py), and by this point in the script CWD is
        # back at the repo root (runsh() pushd/popd's into hiddify-panel/
        # only for the duration of its own install.sh/run.sh, then pops
        # back). Without this, create_app() silently finds no config at
        # all and crashes with "Either 'SQLALCHEMY_DATABASE_URI' or
        # 'SQLALCHEMY_BINDS' must be set" - swallowed by the 2>/dev/null
        # below, so core_type_auto silently never actually ran.
        HIDDIFY_CFG_PATH="$(pwd)/hiddify-panel/app.cfg" python3 -c "
from hiddifypanel.base import create_app
from hiddifypanel.models import ConfigEnum, hconfig, set_hconfig, Domain, DomainType
app = create_app(app_mode='cli')
app.app_context().push()
if hconfig(ConfigEnum.core_type_auto):
    has_xhttp_domain = bool(Domain.query.filter(Domain.mode == DomainType.special_reality_xhttp).first())
    resolved = 'xray' if (hconfig(ConfigEnum.xhttp_enable) or has_xhttp_domain) else 'singbox'
    if resolved != hconfig(ConfigEnum.core_type):
        set_hconfig(ConfigEnum.core_type, resolved)
" 2>/dev/null || warning "core_type auto-resolution failed - keeping previous value for this run."
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
        is_lite() { [[ "$HIDDIFY_PROFILE" == "lite" ]] && echo "0" || echo "$1"; }
        install_run other/dnstt $(is_lite $(hconfig "dnstt_enable")) &

        update_progress "${PROGRESS_ACTION}" "Telegram Proxy" 40
        install_run other/telegram $(is_lite $(hconfig "telegram_enable")) &
        
        update_progress "${PROGRESS_ACTION}" "FakeTlS Proxy" 45
        install_run other/ssfaketls $(is_lite $(hconfig "ssfaketls_enable")) &
        
        # update_progress "${PROGRESS_ACTION}" "V2ray WS Proxy" 50
        # install_run other/v2ray $ENABLE_V2RAY
        
        update_progress "${PROGRESS_ACTION}" "SSH Proxy" 55
        install_run other/ssh 0 &
        
        #update_progress "${PROGRESS_ACTION}" "ShadowTLS" 60
        #install_run other/shadowtls $(hconfig "shadowtls_enable")

        # core_type only decides the PRIMARY core - both cores always run,
        # symmetrically, regardless of which is primary. Every overlapping
        # inbound (vless/vmess/trojan/reality over ws/grpc/tcp/httpupgrade)
        # self-excludes via a `{% if core_type=="xray"|"singbox" %}` gate in
        # its own template, on BOTH sides, so exactly one of the two ever
        # renders a given port - no collision. What's NOT gated, on purpose,
        # is what only one core can serve at all: hysteria2/tuic/
        # shadowsocks2022/anytls/mieru/naive exist ONLY as singbox inbounds
        # (there is no xray/configs/ template for them), while xhttp/xdns/
        # xicmp exist ONLY as xray inbounds (no sing-box equivalent) - each
        # of those needs its one and only core running no matter which core
        # is primary, or it points at a dead port. This used to
        # special-case XRAY_ENABLE=0 under core_type=="singbox" on the
        # theory that "xhttp is already filtered from singbox subs, so it's
        # safe to drop xray" - true but beside the point: a client using the
        # *dedicated Xray-JSON subscription* still needs xhttp (and xdns/
        # xicmp) actually served, singbox-primary or not. The un-gated xray
        # templates were already written assuming "Xray always runs
        # regardless of core_type" (see their own comments) - this was the
        # one place that assumption wasn't actually true. So: both cores
        # simply always run; there is no lean single-core path to keep
        # correct.
        XRAY_ENABLE=1
        SINGBOX_ENABLE=1

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
        error_code=${PIPESTATUS[0]}
    fi
    remove_lock $NAME
else
    if [ -z "$DB_BACKEND" ] && [ -z "$(read_persisted_db_backend)" ] && [ -t 0 ] && [ -t 1 ]; then
        # Only here: this is the one path with a real human at a real
        # terminal (every panel-triggered install/apply/reinstall already
        # passes --no-gui, see commander.py, and skips straight to the
        # other branch), AND a backend was never already chosen (a
        # persisted choice from a prior install means this is a re-run on
        # an existing box, not a fresh one - don't ask again). mysql (the
        # default) is the DB daemon that OOMs first on a small box -
        # sqlite skips a daemon entirely. Exported
        # so the recursive `--no-gui` re-exec below inherits the choice.
        mem_mb=$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)
        recommended=2 # index into db_backends/db_labels below, 1-based
        [ "$mem_mb" -lt 1024 ] && recommended=1
        # db_backends holds the real DB_BACKEND values (other/mysql installs
        # MariaDB, not MySQL - only the label says so, the value install.sh
        # branches on downstream stays "mysql")
        db_backends=(sqlite mysql postgres)
        db_labels=(sqlite mariadb postgres)
        echo ""
        echo "Select a database backend (detected ${mem_mb}MB RAM):"
        for i in "${!db_labels[@]}"; do
            n=$((i + 1))
            [ "$n" -eq "$recommended" ] && echo "  $n) ${db_labels[$i]} (recommended)" || echo "  $n) ${db_labels[$i]}"
        done
        db_choice=""
        while true; do
            read -rp "Backend [$recommended]: " db_choice
            db_choice="${db_choice:-$recommended}"
            if [[ "$db_choice" =~ ^[1-9][0-9]*$ ]] && [ "$db_choice" -le "${#db_backends[@]}" ]; then
                break
            fi
            echo "Enter a number between 1 and ${#db_backends[@]}."
        done
        export DB_BACKEND="${db_backends[$((db_choice - 1))]}"
    fi
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
