#!/usr/bin/env bash
set -e
curl -s http://127.0.0.1:8084/api/health
echo
curl -s http://127.0.0.1:8084/api/db/health
echo
