# Gated tips (appended to the operator mission by scripts/local_relay_run.sh)

- Re-run the failed relay segment end-to-end after any navigation code change, because unit tests and linters do not exercise the PyBoy game loop and a 'passing test suite' does not prove the agent can navigate the gym interior. _(gated; gym-fix-validation-gap)_
