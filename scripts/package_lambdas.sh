#!/bin/bash
set -e
FUNCTIONS=(invoice_create invoice_get invoice_list invoice_update payment_reminder ai_collections invoice_pdf analytics weekly_report)
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
  # __pycache__/*.pyc files embed a hash/mtime of the .py source they were
  # compiled from, baked in at pip-install time -- before the touch below
  # even runs -- so they differ on every install regardless of timestamp
  # normalization. Lambda recompiles on cold start anyway; deleting them
  # is both the fix and a bit less to upload.
  find . -type d -name "__pycache__" -exec rm -rf {} +
  # Normalize every file's mtime before zipping. zip embeds per-file
  # modification times, so without this, identical source produces a
  # different archive (and therefore a different hash) on every packaging
  # run -- pip install timestamps vary run to run even when no dependency
  # changed. That made `terraform plan` treat every Lambda as "changed" on
  # every apply, forcing a re-upload and function update regardless of
  # whether the code actually did.
  find . -exec touch -t 202001010000 {} +
  # Mtime alone wasn't enough -- zip also archives files in filesystem
  # readdir order, which isn't stable across separate `pip install` runs
  # even for identical package contents. Sorting the file list before
  # feeding it to zip (via -@, read names from stdin) fixes that too.
  cd package && find . -type f | sort | zip -X ../../../infrastructure/packages/${FUNC}.zip -@ -q
  cd .. && rm -rf package && cd ../..
done
echo "All packages created."
