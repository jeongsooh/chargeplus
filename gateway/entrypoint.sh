#!/bin/bash
exec uvicorn main:app --host ${GATEWAY_HOST:-0.0.0.0} --port ${GATEWAY_PORT:-9000}
