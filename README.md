# Metric collection for Bazel issues


Quick and dirty tooling for metrics collection.

Usage:
1. Create a `secrets.json` file with two fields
```
{
  "client_id" : "...",
  "client_secret" : "..."
}
```
(get those from https://github.com/settings/developers)

1. `issue-stats.py update` will populate some `all-*.json` files with API
   responses from GitHub
1. Run various queries over those with `issue-stats.py report` and
   `issue-stats.py garden`
1. Feel free to modify those - I hope code is self-explanatory.


