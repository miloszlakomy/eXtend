#!/bin/bash

set -e

CLIENT_IP=127.0.0.1
TCP_PORT=6174
UDP_PORT=6174

TMP_DIR=/tmp/extend
PIPE="${TMP_DIR}/pipe"

function fail() {
    echo -e "$1"
    exit 1
}

while [ $# -gt 1 ]; do
    case "$1" in
        -c|--client-ip) shift; CLIENT_IP="$1" ;;
        -t|--tcp-port) shift; TCP_PORT="$1" ;;
        -u|--udp-port) shift; UDP_PORT="$1" ;;
        *) fail "invalid argument: $1" ;;
    esac
    shift
done

function cleanup() {
    echo "* cleaning up"
    rm -rf "${TMP_DIR}"
}

function init() {
    echo "* initializing"
    mkdir -p "${TMP_DIR}"

    trap cleanup EXIT
}

function test_passed() {
    PARENT_PID="$1"
    TEST_NAME="$2"

    echo "test ${TEST_NAME} passed"
}

function test_fail() {
    PARENT_PID="$1"
    TEST_NAME="$2"

    shift
    shift
    MESSAGE="$*"

    echo -e "test ${TEST_NAME} failed:\n" \
            "${MESSAGE}\n"
}

function expect_recv() {
    TEST_NAME="$1"
    LISTEN_PORT="$2"
    EXPECTED_BASE64="$3"

    NC_OUTPUT_FILE=`mktemp`
    EXPECTED_OUTPUT_FILE=`mktemp`

    echo "${EXPECTED_BASE64}" > "${EXPECTED_OUTPUT_FILE}"
    timeout 5 \
        echo "vnc 127.0.0.1 5900" \
            | nc -l -p "${LISTEN_PORT}" \
            | base64 > "${NC_OUTPUT_FILE}" \
        && diff "${EXPECTED_OUTPUT_FILE}" "${NC_OUTPUT_FILE}" >/dev/null \
        && timeout 5 nc -u -l -p 5900 \
        && test_passed $$ "${TEST_NAME}" \
        || test_fail $$ "${TEST_NAME}" \
                     "*** got ***\n`cat ${NC_OUTPUT_FILE}`\n" \
                     "*** expected ***\n`cat ${EXPECTED_OUTPUT_FILE}`" \
        &
}

init

timeout 20 x11vnc -nocursor -clip "800x600+100+100" >/dev/null &

echo "* preparing expects"
expect_recv "receive_resolution" "${TCP_PORT}" "`echo -n '1920 1080' | base64`"
sleep 3

echo "* testing"
for I in `seq 100`; do
    POS=$[ $I * 10 ]
    echo "cursor $POS $POS"
done | nc -u -q1 "${CLIENT_IP}" "${UDP_PORT}"

wait

