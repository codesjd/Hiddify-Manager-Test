#!/bin/bash
cd $(dirname -- "$0")
source ../../common/utils.sh

# DB_BACKEND=timescaledb installs the TimescaleDB apt repo + extension on top
# of Postgres and enables it on the hiddifypanel database. DB_BACKEND=postgres
# (or anything else non-timescaledb) just installs plain PostgreSQL. Either
# way the resulting connection is plain postgresql+psycopg:// - TimescaleDB
# is wire-compatible, it's a Postgres extension, not a different protocol.
WANT_TIMESCALE=0
if [ "$DB_BACKEND" == "timescaledb" ]; then
    WANT_TIMESCALE=1
fi

if [ "$WANT_TIMESCALE" == "1" ]; then
    # TimescaleDB's own apt repo (their Postgres build tracks upstream
    # closely but ships the timescaledb extension package)
    install_package gnupg curl ca-certificates
    if [ ! -f /etc/apt/sources.list.d/timescaledb.list ]; then
        echo "deb https://packagecloud.io/timescale/timescaledb/$(. /etc/os-release && echo $ID)/ $(. /etc/os-release && echo $VERSION_CODENAME) main" \
            | tee /etc/apt/sources.list.d/timescaledb.list
        curl -Lfs https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /etc/apt/trusted.gpg.d/timescaledb.gpg
        apt-get update -y
    fi
    install_package timescaledb-2-postgresql-16 postgresql-16
else
    install_package postgresql postgresql-contrib
fi

systemctl enable postgresql
systemctl start postgresql

if [ ! -f "postgres_pass" ]; then
    echo "Generating a random password..."
    random_password=$(< /dev/urandom tr -dc 'a-zA-Z0-9' | head -c49; echo)
    echo "$random_password" >"postgres_pass"
    chmod 600 "postgres_pass"

    sudo -u postgres psql -v ON_ERROR_STOP=1 <<-EOSQL
        DO \$\$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'hiddifypanel') THEN
            CREATE ROLE hiddifypanel LOGIN PASSWORD '$random_password';
          ELSE
            ALTER ROLE hiddifypanel WITH PASSWORD '$random_password';
          END IF;
        END
        \$\$;
        SELECT 'CREATE DATABASE hiddifypanel OWNER hiddifypanel'
        WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'hiddifypanel')\gexec
        GRANT ALL PRIVILEGES ON DATABASE hiddifypanel TO hiddifypanel;
EOSQL

    if [ "$WANT_TIMESCALE" == "1" ]; then
        sudo -u postgres psql -d hiddifypanel -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
    fi

    echo "PostgreSQL setup complete."
fi

# Local-only access (same posture as the mariadb install: don't listen on
# the public interface, only 127.0.0.1/socket).
PG_CONF=$(sudo -u postgres psql -tAc "SHOW config_file;" 2>/dev/null)
if [ -n "$PG_CONF" ] && ! grep -q "^listen_addresses\s*=\s*'localhost'" "$PG_CONF"; then
    sed -i "s/^#\?listen_addresses\s*=.*/listen_addresses = 'localhost'/" "$PG_CONF"
    systemctl restart postgresql
fi

systemctl start postgresql
