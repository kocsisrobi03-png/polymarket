# Polymarket Focus Bridge

## Daily ops

### Health
```bash
make health
```

### Smoke test
```bash
make smoke
```

### Restart and verify
```bash
make verify
```

### Service status
```bash
make status
```

### Recent logs
```bash
make log
```

### Latest export files
```bash
make latest
```

## Important files

- `smoke_test_bridge.sh` — endpoint smoke test with assertions
- `restart_and_verify.sh` — restart service, wait for health, run smoke test
- `Makefile` — shortcut commands for daily operations

## Service

- `polymarket-focus-bridge.service`

## Recent ops commits

- `a4f9735` add make targets for bridge ops
- `d0d8418` add restart and verify helper
- `010b888` make bridge smoke test assert responses
