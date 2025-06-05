#!/bin/bash
cd /home/kavia/workspace/code-generation/eventease-45884-9d464e7c/eventease_backend
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

