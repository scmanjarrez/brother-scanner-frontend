#!/usr/bin/env bash
set -euo pipefail

rootfs=/rootfs
busybox_binary=${1:?Path to the static BusyBox binary is required}

copy_file() {
    local source_path=$1
    local target_path="$rootfs$source_path"

    if [[ ! -e $source_path && ! -L $source_path ]]; then
        printf 'Required runtime file is missing: %s\n' "$source_path" >&2
        exit 1
    fi

    mkdir -p "$(dirname "$target_path")"
    cp -a "$source_path" "$target_path"
}

copy_tree() {
    local source_path=$1

    if [[ ! -e $source_path && ! -L $source_path ]]; then
        return 0
    fi

    mkdir -p "$rootfs$(dirname "$source_path")"
    cp -a "$source_path" "$rootfs$(dirname "$source_path")/"
}

copy_library() {
    local library_path=$1

    if [[ ! -f $library_path ]]; then
        printf 'Dynamic library is missing: %s\n' "$library_path" >&2
        exit 1
    fi

    cp --parents --dereference "$library_path" "$rootfs"
}

copy_dynamic_dependencies() {
    local binary_path=$1
    local dependency_output

    if ! dependency_output=$(ldd "$binary_path" 2>&1); then
        if [[ $dependency_output == *'not a dynamic executable'* ]]; then
            return 0
        fi

        printf 'Cannot inspect dependencies for %s:\n%s\n' \
            "$binary_path" "$dependency_output" >&2
        exit 1
    fi

    if [[ $dependency_output == *'not found'* ]]; then
        printf 'Unresolved dependency for %s:\n%s\n' \
            "$binary_path" "$dependency_output" >&2
        exit 1
    fi

    while IFS= read -r library_path; do
        copy_library "$library_path"
    done < <(
        awk '
            $2 == "=>" && $3 ~ /^\// { print $3 }
            $1 ~ /^\// { print $1 }
        ' <<< "$dependency_output"
    )
}

mkdir -p "$rootfs/bin" "$rootfs/usr/bin"
install -m 0755 "$busybox_binary" "$rootfs/bin/busybox"
"$rootfs/bin/busybox" --install -s "$rootfs/bin"
"$rootfs/bin/busybox" --install -s "$rootfs/usr/bin"

for applet_path in "$rootfs"/bin/* "$rootfs"/usr/bin/*; do
    if [[ -L $applet_path ]] && \
        [[ $(readlink "$applet_path") == "$rootfs/bin/busybox" ]]; then
        ln -snf /bin/busybox "$applet_path"
    fi
done

for source_path in \
    /app \
    /etc \
    /home/app \
    /opt/brother \
    /opt/venv \
    /run/cups \
    /usr/lib/cups \
    /usr/lib/i386-linux-gnu/gconv \
    /usr/lib/locale \
    /usr/lib/x86_64-linux-gnu/gconv \
    /usr/lib/x86_64-linux-gnu/ghostscript \
    /usr/lib/x86_64-linux-gnu/sane \
    /usr/lib64/sane \
    /usr/share/color \
    /usr/share/cups \
    /usr/share/fontconfig \
    /usr/share/fonts \
    /usr/share/ghostscript \
    /usr/share/poppler \
    /usr/share/ppd \
    /usr/share/zoneinfo \
    /var/cache/cups \
    /var/log/cups \
    /var/spool/cups; do
    copy_tree "$source_path"
done

copy_tree /usr/local/lib/python3.12
rm -rf \
    "$rootfs/usr/local/lib/python3.12/ensurepip" \
    "$rootfs/usr/local/lib/python3.12/idlelib" \
    "$rootfs/usr/local/lib/python3.12/lib2to3" \
    "$rootfs/usr/local/lib/python3.12/pydoc_data" \
    "$rootfs/usr/local/lib/python3.12/site-packages" \
    "$rootfs/usr/local/lib/python3.12/tkinter"
rm -f "$rootfs/usr/local/lib/python3.12/lib-dynload/_tkinter."*.so
rm -f \
    "$rootfs/opt/brother/scanner/brscan4/brscan_gnetconfig" \
    "$rootfs/opt/brother/scanner/brscan4/brscan_cnetconfig"

for source_path in \
    /bin/bsd-csh \
    /usr/bin/gs \
    /usr/bin/lp \
    /usr/bin/lpoptions \
    /usr/bin/lpstat \
    /usr/bin/pdftops \
    /usr/bin/scanimage \
    /usr/local/bin/python3 \
    /usr/local/bin/python3.12 \
    /usr/sbin/cupsd \
    /usr/sbin/gosu \
    /usr/sbin/lpadmin; do
    copy_file "$source_path"
done

ln -sfn bsd-csh "$rootfs/bin/csh"
ln -sfn \
    /opt/brother/scanner/brscan4/brsaneconfig4 \
    "$rootfs/usr/bin/brsaneconfig4"
ln -sfn /run "$rootfs/var/run"

mkdir -p \
    "$rootfs/dev" \
    "$rootfs/proc" \
    "$rootfs/run/cups" \
    "$rootfs/tmp" \
    "$rootfs/var/cache/cups" \
    "$rootfs/var/lib/cups" \
    "$rootfs/var/log/cups" \
    "$rootfs/var/spool/cups"
chmod 1777 "$rootfs/tmp"

while IFS= read -r -d '' binary_path; do
    case "$binary_path" in
        */brscan_gnetconfig|*/brscan_cnetconfig)
            continue
            ;;
    esac

    copy_dynamic_dependencies "$binary_path"
done < <(
    find -L \
        /opt/brother \
        /usr/lib/cups \
        /usr/lib64/sane \
        /usr/lib/x86_64-linux-gnu/sane \
        -type f -print0
)

while IFS= read -r -d '' binary_path; do
    copy_dynamic_dependencies "$binary_path"
done < <(
    find -L \
        /opt/venv \
        -type d -name '*.libs' -prune -o \
        -type f \( -name '*.so' -o -name '*.so.*' \) -print0
)

while IFS= read -r -d '' binary_path; do
    copy_dynamic_dependencies "$binary_path"
done < <(
    find -L /usr/local/lib/python3.12/lib-dynload \
        -type f \( -name '*.so' -o -name '*.so.*' \) \
        ! -name '_tkinter*' -print0
)

for binary_path in \
    /bin/bsd-csh \
    /usr/bin/gs \
    /usr/bin/lp \
    /usr/bin/lpoptions \
    /usr/bin/lpstat \
    /usr/bin/pdftops \
    /usr/bin/scanimage \
    /usr/local/bin/python3.12 \
    /usr/sbin/cupsd \
    /usr/sbin/gosu \
    /usr/sbin/lpadmin; do
    copy_dynamic_dependencies "$binary_path"
done

for module_path in \
    /usr/lib/i386-linux-gnu/libnss_dns.so.2 \
    /usr/lib/i386-linux-gnu/libnss_files.so.2 \
    /usr/lib/x86_64-linux-gnu/libnss_dns.so.2 \
    /usr/lib/x86_64-linux-gnu/libnss_files.so.2; do
    if [[ -e $module_path ]]; then
        copy_file "$module_path"
        copy_dynamic_dependencies "$module_path"
    fi
done
