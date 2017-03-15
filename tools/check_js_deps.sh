#!/bin/bash

set -ex

CHECKER='./node_modules/.bin/check-dependencies'

if [[ ! -x ${CHECKER} ]]; then
    npm install check-dependencies > /dev/null 2>&1
fi

# We suppress output for the next command because, annoyingly, it reports
# that a dependency is unsatisfied even if the --install flag is specified,
# and that package has been successfully installed
${CHECKER} --install > /dev/null 2>&1

# Print report, if any unsatisfied dependencies remain
if ${CHECKER}; then
    echo "✓ All Javascript dependencies satisfied."
fi
