import multiprocessing

from prometheus_client import multiprocess

bind = "unix:///tmp/gunicorn.sock"

workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"


def child_exit(_, worker):
    multiprocess.mark_process_dead(worker.pid)
