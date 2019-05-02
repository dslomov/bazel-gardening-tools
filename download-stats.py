#! /usr/bin/env python3

import argparse
import datetime
import urllib

import github


REPOS = [
  'bazelbuild/starlark',
  'bazelbuild/bazel-website',
  'bazelbuild/bazel-skylib',
  'bazelbuild/bazel',
]


def update_download_counts(all_repos=False):
  repos = REPOS
  if all_repos:
    repos = github.fetch_repos('bazelbuild')
    print(repos)
  tag = datetime.datetime.now().strftime('%Y-%m-%d')
  with open('downloads.%s' % tag, 'w') as out:
    for repo in repos:
      try:
        releases = github.fetch_releases(repo)
        for release in releases:
          for asset in release['assets']:
            out.write('%s|%s|%d\n' % (tag, asset['name'], asset['download_count']))
      except urllib.error.HTTPError as e:
        print('Skipping %s: %s' % (repo, e))


def main():
    parser = argparse.ArgumentParser(description="Gather Bazel metrics")
    subparsers = parser.add_subparsers(dest="command", help="select a command")

    update_parser = subparsers.add_parser("update", help="update the datasets")
    update_parser.add_argument(
        "--all", action='store_true',
        help="Get all repositories rather than just the select ones")

    args = parser.parse_args()
    if args.command == "update":
        update_download_counts(args.all)
    else:
        parser.print_usage()


main()
