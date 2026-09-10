#!/usr/bin/env bash
set -Eeuo pipefail

readonly HOME_DIR="/home/ubuntu"
readonly DRY_RUN="${HEDGE_CLEANUP_DRY_RUN:-0}"
readonly DOCKER_BUILD_CACHE_RETENTION="168h"
readonly DOCKER_IMAGE_RETENTION="720h"
readonly STOPPED_CONTAINER_LOG_MIN_BYTES=$((100 * 1024 * 1024))
readonly JOURNAL_RETENTION="14d"
readonly JOURNAL_MAX_SIZE="200M"

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
        log "[dry-run] would delete rebuildable cache directory: ${target}"
        return 0
    fi
    find "${target}" -depth -delete
}

cleanup_docker() {
    if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
        log "Docker is unavailable; skipping Docker cleanup."
        return 0
    fi

    log "Pruning unused Docker build cache older than ${DOCKER_BUILD_CACHE_RETENTION}."
    run docker builder prune --all --force --filter "until=${DOCKER_BUILD_CACHE_RETENTION}"

    log "Pruning unused Docker images older than ${DOCKER_IMAGE_RETENTION}."
    log "Docker containers and volumes are intentionally not pruned."
    run docker image prune --all --force --filter "until=${DOCKER_IMAGE_RETENTION}"
}

cleanup_stopped_container_logs() {
    if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
        return 0
    fi

    local docker_root
    local container_id
    local status
    local driver
    local log_path
    local log_bytes
    local container_name
    docker_root="$(docker info --format '{{.DockerRootDir}}')"
    log "Truncating only json-file logs over $((STOPPED_CONTAINER_LOG_MIN_BYTES / 1024 / 1024)) MiB for stopped containers."

    while read -r container_id; do
        [[ -n "${container_id}" ]] || continue
        status="$(docker inspect -f '{{.State.Status}}' "${container_id}")"
        case "${status}" in
            exited|dead) ;;
            *) continue ;;
        esac

        driver="$(docker inspect -f '{{.HostConfig.LogConfig.Type}}' "${container_id}")"
        [[ "${driver}" == "json-file" ]] || continue
        log_path="$(docker inspect -f '{{.LogPath}}' "${container_id}")"

        # Accept only Docker's own per-container json log path.
        case "${log_path}" in
            "${docker_root%/}"/containers/*/*-json.log) ;;
            *)
                log "Skipping unexpected Docker log path: ${log_path}"
                continue
                ;;
        esac
        [[ -f "${log_path}" ]] || continue
        log_bytes="$(stat -c '%s' "${log_path}")"
        (( log_bytes > STOPPED_CONTAINER_LOG_MIN_BYTES )) || continue
        container_name="$(docker inspect -f '{{.Name}}' "${container_id}")"

        if [[ "${DRY_RUN}" == "1" ]]; then
            log "[dry-run] would truncate ${container_name} (${log_bytes} bytes): ${log_path}"
        else
            truncate -s 0 -- "${log_path}"
            log "Truncated ${container_name} (${log_bytes} bytes): ${log_path}"
        fi
    done < <(docker ps -aq)
}

cleanup_pip_cache() {
    local pip_cache="${HOME_DIR}/.cache/pip"
    [[ -d "${pip_cache}" ]] || return 0
    log "Purging pip's rebuildable download cache."
    if [[ "${DRY_RUN}" == "1" ]]; then
        log "[dry-run] would run pip cache purge for ${pip_cache}."
    else
        runuser -u ubuntu -- python3 -m pip cache purge
    fi
}

cleanup_browser_caches() {
    local cache_dir
    local found=0
    local browser_processes='playwright|puppeteer|chromium|chrome|firefox'

    if pgrep -u ubuntu -f "${browser_processes}" >/dev/null 2>&1; then
        log "Browser test activity detected; skipping browser cache cleanup."
        return 0
    fi

    for cache_dir in \
        "${HOME_DIR}/.cache/ms-playwright" \
        "${HOME_DIR}/.cache/playwright" \
        "${HOME_DIR}/.cache/puppeteer"; do
        [[ -d "${cache_dir}" ]] || continue
        found=1
        log "Cleaning rebuildable browser test cache: ${cache_dir}"
        delete_tree "${cache_dir}"
    done

    [[ "${found}" -eq 1 ]] || log "No standard Playwright/browser test cache found."
}

cleanup_system_journals() {
    log "Removing archived journals older than ${JOURNAL_RETENTION}, capped at ${JOURNAL_MAX_SIZE}."
    run journalctl --vacuum-time="${JOURNAL_RETENTION}" --vacuum-size="${JOURNAL_MAX_SIZE}"
}

main() {
    exec 9>/run/lock/hedge-safe-cleanup.lock
    if ! flock -n 9; then
        log "Another cleanup is already running; exiting."
        exit 0
    fi

    log "Starting HEDGE approved safe weekly cleanup (dry_run=${DRY_RUN})."
    df -h /
    cleanup_docker
    cleanup_stopped_container_logs
    cleanup_pip_cache
    cleanup_browser_caches
    cleanup_system_journals
    df -h /
    log "Cleanup completed successfully. No Docker volumes or containers were pruned."
}

main "$@"
