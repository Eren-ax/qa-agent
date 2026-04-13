# Python-boilerplate

> A brief description of your project, what it is used for and how does life get awesome when someone starts to use it.

This repository is boilerplate for golang.
Please find the parts that say 'FIXED_ME' and use them after modifying them.

## Features

> What's all the bells and whistles this project can perform?

- What's the main functionality
- You can also do another thing
- If you get really randy, you can even do this
- Built-in Prometheus metrics instrumentation for request latency insights

## Installing / Getting started

> A quick introduction of the minimal setup you need to get a hello world up & running.
> ...

## Initial Configuration

> A quick introduction of the minimal setup you need to get a hello world up &
> running.

### Setup for development mode

```bash
make setup
```

### Run application in development mode

```bash
# default port is `8088`
make dev
```

### Run linter and formatter

```bash
make pretty
```

### Run pytest

```bash
make test
```

## Prometheus metrics

- Metrics endpoint: `GET /metrics`
- Additional custom metrics can be registered whenever you need them

## Reference

> link for related documents.
