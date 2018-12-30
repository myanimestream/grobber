#!/usr/bin/env bash

export prometheus_multiproc_dir=/tmp/prometheus;
mkdir -p ${prometheus_multiproc_dir};
rm -r ${prometheus_multiproc_dir}/*;

gunicorn --config /app/gunicorn.py grobber:app;