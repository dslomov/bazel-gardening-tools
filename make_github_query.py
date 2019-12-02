#!/usr/bin/env python3

import argparse
import urllib

import github


DEFAULT_REPOS = [
    'bazelbuild/bazel',
]

def generate_untriaged_issue_url(repo, labels):
  args = [
    'utf8=%E2%9C%93'
  ]
  q = [
    'is%3Aissue',
    'is%3Aopen',
    '-label%3Arelease'
  ]
  for label in labels:
    name = label['name']
    if name.lower().startswith('team-'):
      q.append('-label%%3A%s' % name)
  args.append('q=%s' % '+'.join(q))
  url = 'https://github.com/%s/issues?%s' % (repo, '&'.join(args))
  # https://github.com/bazelbuild/bazel/issues?utf8=%E2%9C%93&q=is%3Aissue+is%3Aopen+-label%3Ateam-starlark+-label%3Ateam-ExternalDeps+-label%3Ateam-Rules_java
  return url


def main():
  parser = argparse.ArgumentParser(description='Collect Bazel repo download metrics')

  parser.add_argument(
      '--all', action='store_true',
      help='Get all repositories rather than just the select ones')
  parser.add_argument(
      '--repo_list_file', action='store',
      help='Get repositories listed in this file')

  args = parser.parse_args()
  repos = DEFAULT_REPOS
  if args.all:
    repos = github.fetch_repos('bazelbuild')
  if args.repo_list_file:
    with open(args.repo_list_file, 'r') as rf:
      repos = [l.strip() for l in rf.read().strip().split('\n')]

  for repo in repos:
    labels = github.fetch_labels(repo)
    print(generate_untriaged_issue_url(repo, labels))


if __name__ == '__main__':
  main()
