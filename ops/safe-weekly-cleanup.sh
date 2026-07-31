#!/usr/bin/env bash
set -Eeuo pipefail

readonly HOME_DIR="/home/ubuntu"
readonly MOBILE_PROJECT="${HOME_DIR}/HEDGE-Mobile"
readonly DRY_RUN="${HEDGE_CLEANUP_DRY_RUN:-0}"

log() {
    printf '%s %s\n' "$(date --iso-8601=seconds)" "$*"
}

run() {
    if [[ "${DRY_RUN}" == "1" ]]; then
        printf '[dry-run]'
        printf ' %q' "$@"
        printf '\n'
        return 0
    fi
    "$@"
}

delete_tree() {
    local target="$1"
    [[ -d "${target}" ]] || return 0
    if [[ "${DRY_RUN}" == "1" ]]; then
        log "[dry-run] would delete rebuildable directory: ${target}"
        return 0
    fi
    find "${target}" -depth -delete
}

has_recent_files() {
    local target="$1"
    local days="$2"
    find "${target}" -type f -mtime "-${days}" -print -quit 2>/dev/null | grep -q .
}

cleanup_docker() {
    if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
        log "Docker is unavailable; skipping Docker cleanup."
        return
    fi

    log "Pruning unused Docker build cache older than 7 days."
    run docker builder prune --all --force --filter "until=168h"

    log "Pruning dangling Docker images older than 30 days."
    run docker image prune --force --filter "until=720h"

    # Intentionally do not run docker volume prune or docker system prune.
}

cleanup_pip_cache() {
    local pip_cache="${HOME_DIR}/.cache/pip"
    [[ -d "${pip_cache}" ]] || return 0
    log "Purging pip's rebuildable download cache."
    if [[ "${DRY_RUN}" == "1" ]]; then
        log "[dry-run] would run pip cache purge."
    else
        runuser -u ubuntu -- python3 -m pip cache purge || log "pip cache purge returned non-zero; continuing."
    fi
}

cleanup_flutter() {
    local build_dir="${MOBILE_PROJECT}/build"
    [[ -d "${build_dir}" ]] || return 0

    if pgrep -u ubuntu -f "${MOBILE_PROJECT}|flutter_tools.*(run|build)|GradleDaemon" >/dev/null 2>&1; then
        log "Flutter or Gradle activity detected; skipping Flutter cleanup."
        return
    fi
    if has_recent_files "${build_dir}" 8; then
        log "Flutter build contains files newer than 8 days; keeping it."
        return
    fi

    log "Cleaning inactive Flutter build output."
    if [[ "${DRY_RUN}" == "1" ]]; then
        log "[dry-run] would run flutter clean in ${MOBILE_PROJECT}."
    else
        runuser -u ubuntu -- bash -lc "cd '${MOBILE_PROJECT}' && '${HOME_DIR}/flutter/bin/flutter' clean"
    fi
}

cleanup_gradle_cache() {
    local gradle_cache="${HOME_DIR}/.gradle/caches"
    [[ -d "${gradle_cache}" ]] || return 0

    if pgrep -u ubuntu -f "GradleDaemon|gradlew" >/dev/null 2>&1; then
        log "Gradle activity detected; skipping Gradle cache cleanup."
        return
    fi
    if has_recent_files "${gradle_cache}" 15; then
        log "Gradle cache contains files newer than 15 days; keeping it."
        return
    fi

    log "Deleting inactive Gradle cache; wrapper distributions are preserved."
    delete_tree "${gradle_cache}"
}

cleanup_vscode_servers() {
    local servers_dir="${HOME_DIR}/.vscode-server/cli/servers"
    local server
    [[ -d "${servers_dir}" ]] || return 0

    shopt -s nullglob
    for server in "${servers_dir}"/Stable-*; do
        [[ -d "${server}" ]] || continue
        if pgrep -u ubuntu -f "${server}" >/dev/null 2>&1; then
            log "VS Code server is active; keeping ${server##*/}."
            continue
        fi
        if find "${server}" -maxdepth 0 -mtime +14 -print -quit | grep -q .; then
            log "Deleting inactive VS Code server older than 14 days: ${server##*/}."
            delete_tree "${server}"
        fi
    done
}

cleanup_system_caches() {
    log "Capping persistent system journals at 200 MB."
    run journalctl --vacuum-size=200M

    if command -v apt-get >/dev/null 2>&1; then
        log "Cleaning downloaded apt package files."
        run apt-get clean
    fi
}

main() {
    exec 9>/run/lock/hedge-safe-cleanup.lock
    if ! flock -n 9; then
        log "Another cleanup is already running; exiting."
        exit 0
    fi

    log "Starting HEDGE safe weekly cleanup (dry_run=${DRY_RUN})."
    df -h /
    cleanup_docker
    cleanup_pip_cache
    cleanup_flutter
    cleanup_gradle_cache
    cleanup_vscode_servers
    cleanup_system_caches
    df -h /
    log "Cleanup completed."
}

main "$@"
