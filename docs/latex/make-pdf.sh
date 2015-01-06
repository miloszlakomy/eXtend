#!/bin/bash

OUTPUT_DIR=./out

function die() {
    echo "$@" >&2
    exit 2
}

function to_pdf() {
    [[ $# -ne 1 ]] && die "to_pdf expects a single argument, $# given"

    TEMP=`mktemp -d`
    BASENAME=$(basename $1)
    BASENAME=${BASENAME%.*}

    echo "converting $1"
    echo "  - pass 1"
    OUTPUT=$(pdflatex -output-directory $TEMP -halt-on-error "$1")
    [[ "$?" -eq 0 ]] || die "$OUTPUT"

    echo "  - pass 2"
    OUTPUT=$(pdflatex -output-directory $TEMP -halt-on-error "$1")
    [[ "$?" -eq 0 ]] || die "$OUTPUT"

    mkdir -p "$OUTPUT_DIR"
    cp "$TEMP/${BASENAME}.pdf" "$OUTPUT_DIR"
}

[[ "$#" -gt 0 ]] || die "usage: $0 file [ file2 ... ]"

if [[ ! -d "./img" ]]; then
    rm -f img.tgz \
        && wget http://student.agh.edu.pl/~mradomsk/private/img.tgz \
        && tar zxvf img.tgz \
        || die "cannot download images"
fi

while [[ "$#" -gt 0 ]]; do
    to_pdf "$1"
    shift
done

