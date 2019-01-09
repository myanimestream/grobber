# ===========
#   grobber
# ===========
FROM python:3.7

LABEL maintainer="simon@siku2.io"
EXPOSE 80

# nginx / supervisor
RUN apt-get update \
    && apt-get dist-upgrade -yq \
    && apt-get install -yq nginx supervisor

RUN apt-get clean \
    && rm -rf /var/lib/apt/lists/

RUN echo "\ndaemon off;" >> /etc/nginx/nginx.conf \
    && rm /etc/nginx/sites-available/default

# grobber setup
RUN pip install gunicorn uvicorn pipenv

COPY Pipfile Pipfile.lock ./
RUN pipenv install --system --deploy

WORKDIR /app

COPY data data
COPY grobber grobber
COPY .docker/gunicorn.py ./

COPY .docker/nginx.conf /etc/nginx/conf.d/
COPY .docker/run_gunicorn.sh /usr/bin/run_gunicorn.sh
COPY .docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

RUN chmod +x /usr/bin/run_gunicorn.sh

CMD ["/usr/bin/supervisord"]
