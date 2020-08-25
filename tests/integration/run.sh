#!/bin/bash

set -exu

# Override this to use another ET instance:
export ERRATA_TOOL_URL="${ERRATA_TOOL_URL:-http://localhost:3000}"

# Use our local errata-tool-ansible Git clone:
export ANSIBLE_LIBRARY=$(pwd)/library
export ANSIBLE_MODULE_UTILS=$(pwd)/module_utils

# We're always going to use non-kerberos auth for testing
export ERRATA_TOOL_AUTH=notkerberos

playbooks=($(ls tests/integration/*/main.yml))

for playbook in "${playbooks[@]}"; do
  ansible-playbook -vvv $playbook
done
