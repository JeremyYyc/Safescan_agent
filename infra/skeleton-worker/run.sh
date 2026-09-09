#!/bin/sh
set -eu

echo "${WORKER_NAME} skeleton started"
trap 'exit 0' TERM INT
while :; do
  sleep 30 &
  wait $!
done
