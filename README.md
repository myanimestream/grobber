# Grobber

A [quart] api server serving Anime data.

## Docker

The `docker-compose.yml` file has a complete setup for Grobber to run,
it already comes with [Nginx] as a reverse proxy,
a [MongoDB] database, a slightly modified version of [Scylla]
(which supports HTTPS) and [Browserless] for browser emulation.

### Environment
- `MONGO_URI`:
    Mongo database uri to connect to
- `PROXY_URL`:
    Specify proxy to use (recommended to avoid ip-block)
- `CHROME_WS`:
    while technically optional, it is strongly recommended to use an
    external chrome browser such as [Browserless]
- `SENTRY_DSN`:
    If you want some sweet error reports, there's a [Sentry] integration.



[browserless]: https://www.browserless.io/ "Browserless website"
[nginx]: https://www.nginx.com/ "NginX website"
[mongodb]: https://www.mongodb.com/ "MongoDB website"

[quart]: https://pgjones.gitlab.io/quart/ "Basically Flask, but async"
[scylla]: https://github.com/MyAnimeStream/scylla