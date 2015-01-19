#!/bin/bash

set -e

function die() {
    echo "$@" >&2
    exit 1
}

SCRIPT_DIR=$(dirname $(readlink -f "$0"))
LIB_DIR="$SCRIPT_DIR/libs"

git submodule update --init

pushd "$LIB_DIR" >/dev/null 2>&1
    echo "* netifaces: downloading"
    NETIFACES_RELEASE=release_0_10_4.tar.gz
    #rm -f ./"$NETIFACES_RELEASE"
    #wget -q https://bitbucket.org/al45tair/netifaces/get/"$NETIFACES_RELEASE"

    echo "* netifaces: unpacking"
    NETIFACES_DIR=$(tar tf "$NETIFACES_RELEASE" | head -n 1 | sed 's|/[^/]*||')
    tar xf "$NETIFACES_RELEASE"

    pushd "$NETIFACES_DIR" >/dev/null 2>&1
        echo "* netifaces: patching"
        sed -i -e 's/^#define _WIN32_WINNT .*$/#define _WIN32_WINNT 0x600/' netifaces.c

        INCLUDE_DIR_32BIT="$(mktemp -d)"
        pushd "$INCLUDE_DIR_32BIT" >/dev/null 2>&1
            SUBDIR="i386-linux-gnu/python2.7"
            mkdir -p "$SUBDIR"
            cat > "$SUBDIR/pyconfig.h" <<EOF
#include <linux/if_packet.h>
EOF
        popd >/dev/null 2>&1

        echo "* netifaces: compiling for linux (32bit)"
        gcc -m32 -I/usr/include/python2.7 -isystem "$INCLUDE_DIR_32BIT" -fPIC -shared -DHAVE_GETIFADDRS -o netifaces.i386.so netifaces.c

        echo "* netifaces: compiling for linux (64bit)"
        gcc -I/usr/include/python2.7 -fPIC -shared -DHAVE_GETIFADDRS -o netifaces.x86_64.so netifaces.c

        if false; then
            echo "* netifaces: compiling for win32"
            TMPDIR=$(mktemp -d)
            cp -R /usr/include/python2.7/* "$TMPDIR"
            >"$TMPDIR/pyconfig.h"
            i686-w64-mingw32-gcc -I"$TMPDIR" -shared -DHAVE_GETIFADDRS -DWIN32 -o netifaces.dll netifaces.c
        fi

        echo "* netifaces: copying .so to libs/"
        mkdir -p "$LIB_DIR/x86_64" "$LIB_DIR/i386"
        cp -f netifaces.i386.so "$LIB_DIR/i386/netifaces.so"
        cp -f netifaces.x86_64.so "$LIB_DIR/x86_64/netifaces.so"
        rm -f "$LIB_DIR/netifaces.so"
        ln -s "$LIB_DIR/$(uname -p)/netifaces.so" "$LIB_DIR/netifaces.so"
    popd >/dev/null 2>&1

    echo "* netifaces: cleaning up"
    #rm -rf "$NETIFACES_DIR" "$NETIFACES_RELEASE"
popd >/dev/null 2>&1
