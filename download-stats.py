#! /usr/bin/env python3

import argparse
import collections
import datetime
import re
import string
import sys
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
  now = datetime.datetime.now()
  ymd = now.strftime('%Y-%m-%d')
  hm = now.strftime('%H%M')
  file_name = 'downloads.%s.%s' % (ymd, hm)
  with open(file_name, 'w') as out:
    for repo in repos:
      try:
        releases = github.fetch_releases(repo)
        for release in releases:
          name_to_counts = {}
          name_to_counts = collections.defaultdict(dict)
          for asset in release['assets']:
            file_name = asset['name']
            count = int(asset['download_count'])
            if file_name.endswith('.sig'):
              file_name = file_name[0:-4]
              name_to_counts[file_name]['sig'] = count
            elif file_name.endswith('.sha256'):
              file_name = file_name[0:-7]
              name_to_counts[file_name]['sha256'] = count
            else:
              name_to_counts[file_name]['bin'] = count

          for file_name, counts in name_to_counts.items():
            out.write('%s|%s|%s|%d|%d|%d\n' % (ymd, hm, file_name,
                                               counts.get('bin') or 0,
                                               counts.get('sha256') or 0,
                                               counts.get('sig') or 0))
      except urllib.error.HTTPError as e:
        print('Skipping %s: %s' % (repo, e))


def ExtractFeature(s, feature_list):
  """Extract a feature from a file name.

  The feature and then redundent punction is removed from the input.

  Returns:
    feature, remainder
  """
  for feature in feature_list:
    pos = s.find(feature)
    if pos >= 0:
      before = s[0:pos]
      after = s[pos+len(feature):]
      if (len(before) > 0 and len(after) > 0
          and before[-1] in string.punctuation
          and after[0] in string.punctuation):
        before = before[0:-1]
      return feature, before + after
  return None, s


def map_raw_data(file_names):
  """Recategorize the download files names into bucketable dimensions.

  This is probably temporary code.

  For each data files:
    Categorize each entry along the important dimensions
      - gather the oddball stuff into an attribute bag for now
    Re-emit that in a form easy to sort and reduce
  """

  version_re = re.compile('[-_.](\d+\.\d+\.\d+[a-z]*)[-_.]')
  jdk_spec_re = re.compile('[^a-z]?(jdk\d*)')

  for f in file_names:
    print('Loading:', f, file=sys.stderr)
    with open(f, 'r') as df:
      for line in df:
        line = line.strip()
        ymd, hm, filename, bin_count, sha_count, sig_count = line.split('|')
        # eat away parts until todo us empty
        todo = filename
        attributes = []

        # msvc was an odd tag added to early versions
        if todo.find('-msvc') > 0:
          attributes.append('msvc')
          todo = todo.replace('-msvc', '')

        ver_match = version_re.search(todo)
        if not ver_match:
          print('Can not find version on:', line, file=sys.stderr)
          continue

        product = todo[0:ver_match.start(0)]
        version = ver_match.group(1)
        todo = todo[ver_match.end(1):]
        arch, todo = ExtractFeature(todo, ['x86_64'])
        os, todo = ExtractFeature(
            todo, ['dist', 'linux', 'darwin', 'macos', 'osx', 'windows'])
        if os in ['darwin', 'osx']:
          os = 'macos'

        # extract sig before packaging, so .sh and .sha256 are not confused
        is_bin = True
        if todo.endswith('.sig'):
          todo = todo[0:-4]
          attributes.append('sig')
          is_bin = False
        elif todo.endswith('.sha256'):
          todo = todo[0:-7]
          attributes.append('sig')
          is_bin = False

        packaging, todo = ExtractFeature(
            todo, ['.exe', '.sh', '.deb', '.rpm', '.zip', '.tar.gz', '.tgz'])
        if packaging and packaging[0] == '.':
          packaging = packaging[1:]
        if packaging in ['tar.gz', 'tgz']:
          if not arch:
            arch = 'src'
          if not os:
            os = 'any'

        installer, todo = ExtractFeature(todo, ['installer'])
        installer = 'installer' if installer else 'standalone'

        # How we say things about JDK is a mess
        nojdk, todo = ExtractFeature(todo, ['without-jdk'])
        jdk = None
        if nojdk:
          jdk = 'nojdk'
        else:
          jdk_match = jdk_spec_re.search(todo)
          if jdk_match:
            jdk = jdk_match.group(1)
            todo = todo[0:jdk_match.start(1)] + todo[jdk_match.end(1):]
          if jdk:
            attributes.append(jdk)

        left = re.sub(r'^[- _.]*', '', todo)
        if left:
          left = ' - LEAVES(%s)' % left
        print('%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|{%s}%s' % (
            filename, ymd, hm, bin_count, sha_count, sig_count,
            product, version, arch, os, packaging, installer,
            is_bin,
            '|'.join(attributes), left))


def main():
    parser = argparse.ArgumentParser(description='Gather Bazel metrics')
    subparsers = parser.add_subparsers(dest='command', help='select a command')

    update_parser = subparsers.add_parser('update', help='update the datasets')
    update_parser.add_argument(
        '--all', action='store_true',
        help='Get all repositories rather than just the select ones')

    # Usage:  download-stats map downloads.*
    map_parser = subparsers.add_parser('map', help='categorize the data')
    map_parser.add_argument(
        'files', nargs=argparse.REMAINDER, help='raw data files')

    args = parser.parse_args()
    if args.command == 'update':
        update_download_counts(args.all)
    elif args.command == 'map':
        map_raw_data(args.files)
    else:
        parser.print_usage()


if __name__ == '__main__':
  main()

