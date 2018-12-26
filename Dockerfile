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

COPY grobber grobber
COPY .docker/gunicorn.py ./

COPY .docker/nginx.conf /etc/nginx/conf.d/
COPY .docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord"]
