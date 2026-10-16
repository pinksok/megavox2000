#!/bin/bash
# Keep this unit identical to GitHub main.
#
# mega is the primary unit: changes are made, committed and pushed there.
# Other units (mega2, the garage boombox) run this from megavox-update.timer
# to pull them. It only updates while nothing is playing, so music is never
# cut off -- the next timer run just tries again.
#
# Everything lives in main() so bash has parsed the whole script before the
# git merge below can replace this file on disk.

main() {
    local repo old state
    repo="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
    cd "$repo" || exit 1

    git fetch -q origin main || { echo "fetch failed (offline?), will retry"; exit 0; }
    [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] && exit 0

    if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
        echo "local edits in $repo -- not updating. Make changes on mega, not here:"
        git status --short --untracked-files=no
        exit 1
    fi

    state=$(curl -s -m 5 localhost:5000/status \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("state",""))' 2>/dev/null)
    case "$state" in
        Playing|Paused|ACQUIRING*) echo "busy ($state), will retry"; exit 0 ;;
    esac

    old=$(git rev-parse HEAD)
    git merge -q --ff-only origin/main || { echo "fast-forward failed"; exit 1; }
    echo "updated $(git rev-parse --short "$old") -> $(git rev-parse --short HEAD)"

    # Installed boot script = template + this unit's user (same as install.sh)
    if ! git diff --quiet "$old" HEAD -- system/megavox-boot.sh; then
        cp system/megavox-boot.sh megavox-boot.sh
        chmod +x megavox-boot.sh
        sed -i "s|^APP_USER=.*|APP_USER=\"$(id -un)\"|" megavox-boot.sh
        echo "reinstalled megavox-boot.sh (takes effect next boot)"
    fi

    if ! git diff --quiet "$old" HEAD -- app; then
        systemctl --user restart megavox2000 && echo "restarted megavox2000"
    fi
}

main "$@"; exit
