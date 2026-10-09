#!/bin/sh
set -eu

tries=0
until lpstat -r >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "$tries" -ge 30 ]; then
        printf '%s\n' 'CUPS no inició dentro del tiempo esperado.' >&2
        exit 1
    fi
    sleep 1
done
sleep 1

if [ -n "${PRINTER_IP:-}" ]; then
    ppd_path=/usr/share/ppd/brother/brother-DCP1610W-cups-en.ppd
    if [ ! -f "$ppd_path" ]; then
        printf '%s\n' "No se encontró el PPD de Brother: $ppd_path" >&2
        exit 1
    fi

    lpadmin -p "${PRINTER_QUEUE:-brother}" -E \
        -v "socket://${PRINTER_IP}:9100" \
        -P "$ppd_path"
    lpoptions -d "${PRINTER_QUEUE:-brother}"

    if ! brsaneconfig4 -q 2>/dev/null | grep -Fq "${PRINTER_IP}"; then
        brsaneconfig4 -a name=Brother model=DCP-1610W "ip=${PRINTER_IP}"
    fi
fi

rm -rf /tmp/brother-scanner
mkdir -p /tmp/brother-scanner
chown app:app /tmp/brother-scanner
chmod 0700 /tmp/brother-scanner

exec gosu app:app gunicorn \
    --bind "0.0.0.0:${PORT:-8080}" \
    --workers 1 \
    --threads 4 \
    --timeout 240 \
    'scanner_app:create_app()'
