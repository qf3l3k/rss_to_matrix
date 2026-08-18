#!/bin/sh

set -eu

SERVICE_USER="rss-to-matrix"
APP_DIR="/opt/rss-to-matrix"
VENV_DIR="${APP_DIR}/.venv"
CONFIG_DIR="/etc/rss-to-matrix"
STATE_DIR="/var/lib/rss-to-matrix"
UNIT_DIR="/etc/systemd/system"

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)

if [ "$(id -u)" -ne 0 ]; then
    printf '%s\n' "This installer must run as root." >&2
    exit 1
fi

for command in python3 systemctl getent groupadd useradd install date; do
    if ! command -v "$command" >/dev/null 2>&1; then
        printf 'Required command not found: %s\n' "$command" >&2
        exit 1
    fi
done

if [ ! -f "${PROJECT_ROOT}/pyproject.toml" ]; then
    printf '%s\n' "Run this installer from a complete project checkout." >&2
    exit 1
fi

timer_was_active=false
if systemctl is-active --quiet rss-to-matrix.timer; then
    timer_was_active=true
fi

finish() {
    status=$?
    trap - EXIT
    if [ "$timer_was_active" = true ] && [ "$status" -eq 0 ]; then
        if ! systemctl start rss-to-matrix.timer; then
            printf '%s\n' "Installation succeeded, but the timer could not restart." >&2
            status=1
        fi
    elif [ "$timer_was_active" = true ]; then
        printf '%s\n' "Installation failed; the timer remains stopped." >&2
    fi
    exit "$status"
}
trap finish EXIT

systemctl stop rss-to-matrix.timer 2>/dev/null || true
systemctl stop rss-to-matrix.service 2>/dev/null || true

if ! getent group "$SERVICE_USER" >/dev/null; then
    groupadd --system "$SERVICE_USER"
fi

if ! getent passwd "$SERVICE_USER" >/dev/null; then
    useradd \
        --system \
        --gid "$SERVICE_USER" \
        --home-dir "$STATE_DIR" \
        --shell /usr/sbin/nologin \
        "$SERVICE_USER"
fi

install -d -m 0755 -o root -g root "$APP_DIR"
install -d -m 0750 -o root -g "$SERVICE_USER" "$CONFIG_DIR"
install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$STATE_DIR"

if [ -f "${STATE_DIR}/state.sqlite3" ]; then
    backup="${STATE_DIR}/state.sqlite3.backup.$(date -u +%Y%m%dT%H%M%SZ)"
    install \
        -m 0640 \
        -o "$SERVICE_USER" \
        -g "$SERVICE_USER" \
        "${STATE_DIR}/state.sqlite3" \
        "$backup"
    printf 'State backup created: %s\n' "$backup"
fi

if [ ! -x "${VENV_DIR}/bin/python" ]; then
    python3 -m venv "$VENV_DIR"
fi
"${VENV_DIR}/bin/pip" install --upgrade "$PROJECT_ROOT"

if [ ! -f "${CONFIG_DIR}/config.toml" ]; then
    install \
        -m 0640 \
        -o root \
        -g "$SERVICE_USER" \
        "${PROJECT_ROOT}/config/config.example.toml" \
        "${CONFIG_DIR}/config.toml"
    printf 'Created configuration: %s\n' "${CONFIG_DIR}/config.toml"
else
    printf 'Preserved existing configuration: %s\n' "${CONFIG_DIR}/config.toml"
fi
chown root:"$SERVICE_USER" "${CONFIG_DIR}/config.toml"
chmod 0640 "${CONFIG_DIR}/config.toml"

install \
    -m 0644 \
    -o root \
    -g root \
    "${PROJECT_ROOT}/systemd/rss-to-matrix.service" \
    "${UNIT_DIR}/rss-to-matrix.service"
install \
    -m 0644 \
    -o root \
    -g root \
    "${PROJECT_ROOT}/systemd/rss-to-matrix.timer" \
    "${UNIT_DIR}/rss-to-matrix.timer"

systemctl daemon-reload

printf '%s\n' "Installation complete."
printf '%s\n' "Review ${CONFIG_DIR}/config.toml, then run:"
printf '  %s\n' "sudo -u ${SERVICE_USER} ${VENV_DIR}/bin/rss-to-matrix validate-config"
printf '  %s\n' "systemctl start rss-to-matrix.service"
printf '  %s\n' "systemctl enable --now rss-to-matrix.timer"
