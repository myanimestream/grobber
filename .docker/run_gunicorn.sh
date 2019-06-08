#!/usr/bin/env bash

gunicorn --config /app/gunicorn.py grobber:app;