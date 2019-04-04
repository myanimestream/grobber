# Grobber
[![FOSSA Status][fossa-status-info]][fossa-status-link]

A [quart] api server serving Anime data.

The server takes a very lazy approach in the sense that it
doesn't do anything unless it has to. This means that the data
is only actually retrieved when it is requested. This results
in some extreme performance penalties. Everything is a race to
make sure the user gets as much data as soon as possible.
This approach has a lot of problems which will be addressed by
a future project called [Cardinal](https://github.com/MyAnimeStream/cardinal)

# JSON API Documentation
You can find a somewhat detailed documentation [here][grobber-documentation].

# Hosting it yourself

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
    If you want some sweet error reports, there's a [Sentry](https://sentry.io/welcome/)
    integration.

[browserless]: https://www.browserless.io/ "Browserless website"
[nginx]: https://www.nginx.com/ "NginX website"
[mongodb]: https://www.mongodb.com/ "MongoDB website"

[quart]: https://pgjones.gitlab.io/quart/ "Basically Flask, but async"
[scylla]: https://github.com/MyAnimeStream/scylla

[grobber-documentation]: https://grobber.docs.apiary.io

[fossa-status-info]: https://app.fossa.io/api/projects/git%2Bgithub.com%2FMyAnimeStream%2Fgrobber.svg?type=shield
[fossa-status-link]: https://app.fossa.io/projects/git%2Bgithub.com%2FMyAnimeStream%2Fgrobber?ref=badge_large