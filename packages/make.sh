#!/bin/bash

make_package() {
    echo "creating package $2 from $1"

    local SRC_DIR=$(readlink -f "$1")
    local CURR_DIR="$(readlink -f .)"
    local PKG_DIR="$CURR_DIR/packages"
    local DST_DIR="$CURR_DIR/files/$2"
    local ARCHIVE_NAME="$2.tar.gz"

    mkdir -p "${DST_DIR}" "$(readlink -f .)/packages"

    local EXTRA_LIBS=""
    local EXTRA_FILES=""

    local LIBS_STARTED=0
    while [[ "$#" -ge 3 ]]; do
        if [[ "$3" == "--libs" ]]; then
            LIBS_STARTED=1
        elif [[ "$LIBS_STARTED" -eq "1" ]]; then
            EXTRA_LIBS="$EXTRA_LIBS $(readlink -f $3)"
        else
            EXTRA_FILES="$EXTRA_FILES $(readlink -f $3)"
        fi

        shift
    done

    local FILES=$(find -L "${SRC_DIR}" -name '*.py')

    echo "* output: $ARCHIVE_NAME"
    rm -rf "${DST_DIR}" "${PKG_DIR}/${ARCHIVE_NAME}"
    mkdir -p "${DST_DIR}"

    echo "* adding $(echo $FILES | wc -w) python source(s) from ${SRC_DIR}"
    for FILE in ${FILES}; do
        local FILE="${FILE:${#SRC_DIR}:${#FILE}}"
        mkdir -p "${DST_DIR}"$(dirname "${FILE}")
        cp "${SRC_DIR}${FILE}" "${DST_DIR}${FILE}"
    done

    for FILE in ${EXTRA_FILES}; do
        local FILE_BASENAME=$(basename "${FILE}")
        echo "* adding $FILE_BASENAME ($FILE)"
        cp -RT "${FILE}" "${DST_DIR}/${FILE_BASENAME}"
    done

    mkdir -p "${DST_DIR}/libs"
    for FILE in ${EXTRA_LIBS}; do
        local FILE_BASENAME=$(basename "${FILE}")
        echo "* adding lib $FILE_BASENAME ($FILE)"
        cp -RT "${FILE}" "${DST_DIR}/libs/${FILE_BASENAME}"
    done

    tar zcf "${PKG_DIR}/${ARCHIVE_NAME}" -C "$(dirname "${DST_DIR}")" "$(basename "${DST_DIR}")"
}

CLIENT_LIB_NAMES="Xlib pkg_resources.py"
CLIENT_LIBS=""
for LIB in $CLIENT_LIB_NAMES; do
    CLIENT_LIBS+=" /usr/lib/python2.7/dist-packages/$LIB"
done

LIBS="../libs/pyfiglet ../libs/pymouse"
for LIB in ../libs/*.py; do
    LIBS+=" $LIB"
done

make_package ../client eXtend-client-linux-64bit --libs ../libs/x86_64/netifaces.so $LIBS $CLIENT_LIBS
make_package ../client eXtend-client-linux-32bit --libs ../libs/i386/netifaces.so $LIBS $CLIENT_LIBS
make_package ../server eXtend-server --libs $LIBS

