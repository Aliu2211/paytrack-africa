#!/bin/bash
set -e
FUNCTIONS=(invoice_create invoice_get invoice_list invoice_update payment_reminder ai_collections invoice_pdf)
mkdir -p infrastructure/packages
for FUNC in ${FUNCTIONS[@]}; do
  cd functions/$FUNC
  # --platform/--only-binary force Lambda-compatible Linux wheels regardless
  # of the host OS -- reportlab/openai bundle compiled dependencies that a
  # plain install on macOS would resolve to non-Linux wheels for.
  pip install -r requirements.txt -t ./package \
    --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 \
    --quiet
  cp handler.py ./package/
  cd package && zip -r ../../../infrastructure/packages/${FUNC}.zip . --quiet
  cd .. && rm -rf package && cd ../..
done
echo "All packages created."
