#!/bin/bash
cd "$(dirname -- "$0")" || exit 1

function main() {
    PORT="${1:-9001}"
    # PORT ends up string-interpolated into a command scheduled via `at`
    # below - an unvalidated value (e.g. containing `;`/`$(...)`) would be
    # command injection into a job that runs unattended in 4 hours. Only a
    # bare 1-65535 port number is ever legitimate here.
    if ! [[ "$PORT" =~ ^[0-9]+$ ]] || ((PORT < 1 || PORT > 65535)); then
        echo "Invalid port: $PORT" >&2
        exit 1
    fi
    echo "we are openning a port on $PORT"
    iptables -I INPUT -p tcp --dport "$PORT" -j ACCEPT
    pids=$(lsof -t -i:"$PORT")
    if [ -n "$pids" ]; then
        kill $pids
    fi
    printf 'pids=$(lsof -t -i:%s); [ -n "$pids" ] && kill $pids\n' "$PORT" | at now + 4 hour
    printf 'iptables -D INPUT -p tcp --dport %s -j ACCEPT\n' "$PORT" | at now + 4 hour
}

main "$@" |& tee ../log/system/temporary_access.log
