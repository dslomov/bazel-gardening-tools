#!/usr/bin/env python3

import argparse
import collections
import datetime
import io
import re
import string
import sys
import urllib

# from google.cloud import storage
import github


DEFAULT_REPOS = [
    'bazelbuild/bazel',
    'bazelbuild/bazel-gazelle',
    'bazelbuild/bazelisk',
    'bazelbuild/bazel-skylib',
    'bazelbuild/bazel-website',
    'bazelbuild/buildtools',
    'bazelbuild/rules_android',
    'bazelbuild/rules_apple',
    'bazelbuild/rules_cc',
    'bazelbuild/rules_docker',
    'bazelbuild/rules_foreign_cc',
    'bazelbuild/rules_kotlin',
    'bazelbuild/rules_python',
    'bazelbuild/rules_rust',
    'bazelbuild/skydoc',
    'bazelbuild/starlark',
]

Bins = collections.namedtuple(
    'Bins',
    'product version arch os packaging installer is_bin attributes leftover')

_PRODUCT_VERSION_RE = re.compile(r'(\w+[-\w]*)[-_.](\d+\.\d+\.\d+[a-z\d]*)[^.\D]?')
_VERSION_RE = re.compile(r'[-_.]v?(\d+\.\d+\.\d+[a-z\d]*(-rc\d+)?)|(\d+\.\d+[a-z\d]*(-rc\d+)?)')
_JDK_SPEC_RE = re.compile(r'[^a-z]?(jdk\d*)')

_LINUX_PACKAGE_EXTENSIONS = ['.sh', '.deb', '.rpm', '.zip', '.tar.gz', '.tgz']
_MACOS_PACKAGE_EXTENSIONS = ['.dmg', '.mac', '.osx']
_WINDOWS_PACKAGE_EXTENSIONS = ['.exe']


def FetchDownloadCounts(repos, storage_bucket=None, folder=None):
  now = datetime.datetime.now()
  ymd = now.strftime('%Y-%m-%d')
  hm = now.strftime('%H%M')
  file_name = 'downloads.%s.%s.txt' % (ymd, hm)

  if storage_bucket:
    out = io.StringIO()
    CollectDownloadCounts(out, repos, ymd, hm)
    if folder:
      # Not using os.path.join because we need gcs path sep.
      file_name = folder + '/' + file_name
    blob = storage_bucket.blob(file_name)
    blob.upload_from_string(out.getvalue(), content_type='text/plain')
  else:
    with open(file_name, 'w') as out:
      CollectDownloadCounts(out, repos, ymd, hm)


def CollectDownloadCounts(out, repos, ymd, hm):
  for repo in repos:
    try:
      releases = github.fetch_releases(repo)
      for release in releases:
        tag = release['tag_name']
        label = '%s/%s' % (repo, tag)
        print('Scanning:', label)
        name_to_counts = collections.defaultdict(dict)
        assets = release.get('assets')
        if not assets:
          err = 'WARNING: %s has no assets' % label
          if release.get('tarball_url') or release.get('zipball_url'):
            err += ', but it does have zip or tar downloads'
          print(err)
          continue
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
          bins = Categorize(file_name, tag)
          if bins:
            out.write('%s|%s|%s|%d|%d|%d|%s|%s|%s|%s|%s|%s|%s|{%s}%s\n' % (
                file_name, ymd, hm, counts.get('bin') or 0,
                counts.get('sha256') or 0, counts.get('sig') or 0,
                bins.product, bins.version, bins.arch, bins.os, bins.packaging,
                bins.installer, bins.is_bin, bins.attributes,
                bins.leftover))

    except urllib.error.HTTPError as e:
      print('Skipping %s: %s' % (repo, e))


def ExtractFeature(s, feature_list):
  """Extract a feature from a file name.

  The feature and then redundant punction is removed from the input.

  Returns:
    feature, remainder
  """
  for feature in feature_list:
    pos = s.find(feature)
    if pos < 0:
      pos = s.find(feature.upper())
    if pos >= 0:
      before = s[0:pos]
      after = s[pos+len(feature):]
      if (len(before) and len(after)
          and before[-1] in string.punctuation
          and after[0] in string.punctuation):
        before = before[0:-1]
        # If we are left with after just being the '-', drop it.
        if len(after) == 1:
          after = ''
      elif len(after) == 0 and before[-1] in string.punctuation:
        before = before[0:-1]
      return feature.lower(), before + after
  return None, s


def MapRawData(file_names):
  """Recategorize the download files names into bucketable dimensions.

  This is used for regression testing changes to the categorizor.

  For each data files:
    Categorize each entry along the important dimensions
      - gather the oddball stuff into an attribute bag for now
    Re-emit that in a form easy to sort and reduce
  """
  for f in file_names:
    print('Loading:', f, file=sys.stderr)
    with open(f, 'r') as df:
      for line in df:
        line = line.strip()
        (file_name, ymd, hm, bin_count, sha_count, sig_count, o_prod,
         o_version, o_arch, o_os, o_packaging, o_installer, o_is_bin,
         o_left) = line.split('|')
        bins = Categorize(file_name, o_version or '@REPO_TAG@')
        if bins:
          print('%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|{%s}%s' % (
              file_name, ymd, hm, bin_count, sha_count, sig_count,
              bins.product, bins.version, bins.arch, bins.os, bins.packaging,
              bins.installer, bins.is_bin, bins.attributes,
              bins.leftover))


def Categorize(file_name, default_version=None):
  """Break down file name into bins that matter."""

  # eat away parts until todo us empty
  todo = file_name
  attributes = []

  # msvc was an odd tag added to early versions
  if todo.find('-msvc') > 0:
    attributes.append('msvc')
    todo = todo.replace('-msvc', '')

  arch, todo = ExtractFeature(todo, ['x86_64', 'amd64'])
  if arch == 'amd64':
    arch = 'x86_64'

  os, todo = ExtractFeature(
      todo, ['dist', 'linux', 'darwin', 'macos', 'osx', 'windows'])
  if os in ['darwin', 'osx']:
    os = 'macos'
  if os == 'dist':
    os = 'any'

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

  packaging, todo = ExtractFeature(todo, _LINUX_PACKAGE_EXTENSIONS +
                                   _MACOS_PACKAGE_EXTENSIONS +
                                   _WINDOWS_PACKAGE_EXTENSIONS)
  if packaging and packaging[0] == '.':
    packaging = packaging[1:]
  if packaging in ['tar.gz', 'tgz']:
    if not arch:
      arch = 'src'
    if not os:
      os = 'any'
  if not os:
    if packaging in _LINUX_PACKAGE_EXTENSIONS:
      os = 'linux'
    if packaging in _MACOS_PACKAGE_EXTENSIONS:
      os = 'macos'
    if packaging in _WINDOWS_PACKAGE_EXTENSIONS:
      os = 'windows'

  installer, todo = ExtractFeature(todo, ['installer'])
  installer = 'installer' if installer else 'standalone'

  # How we say things about JDK is a mess
  nojdk, todo = ExtractFeature(todo, ['without-jdk'])
  jdk = None
  if nojdk:
    jdk = 'nojdk'
  else:
    jdk_match = _JDK_SPEC_RE.search(todo)
    if jdk_match:
      jdk = jdk_match.group(1)
      todo = todo[0:jdk_match.start(1)] + todo[jdk_match.end(1):]
    if jdk:
      attributes.append(jdk)

  # At this point, only the product name and version should be left.
  m = _PRODUCT_VERSION_RE.match(todo)
  if m:
    product = todo[0:m.end(1)]
    version = m.group(2)
    todo = todo[m.end(2):]
  else:
    # Look for a version # at the end of the text
    m = _VERSION_RE.search(todo)
    if m and m.end() == len(todo):
      product = todo[0:m.start()-1]
      version = todo[m.start():m.end()]
      todo = ''
    else:
      # some things are unversioned. e.g. bazelisk-os-arch.
      sep_pos = todo.find('-')
      if sep_pos <= 0:
        # print('Can not find version on:', file_name, file=sys.stderr)
        product = todo
        todo = ''
        version = default_version
      else:
        version = 'head'
        product = todo[0:sep_pos]
        todo = todo[sep_pos:]
  while product.endswith('-') or product.endswith('.'):
    product = product[0:len(product)-1]
  left = re.sub(r'^[- _.]*', '', todo)
  if left:
    left = ' - LEAVES(%s)' % left

  return Bins(product, version, arch, os, packaging, installer, is_bin,
              '|'.join(attributes), left)


def main():
  parser = argparse.ArgumentParser(description='Collect Bazel repo download metrics')
  subparsers = parser.add_subparsers(dest='command', help='select a command')

  update_parser = subparsers.add_parser('update', help='update the datasets')
  update_parser.add_argument(
      '--all', action='store_true',
      help='Get all repositories rather than just the select ones')
  update_parser.add_argument(
      '--repo_list_file', action='store',
      help='Get repositories listed in this file')
  update_parser.add_argument(
      '--bucket', default='',
      help='Write results to GCS bucket')
  update_parser.add_argument(
      '--folder', default=None,
      help='Folder in GCS bucket')
  update_parser.add_argument(
      '--save_cloud', action='store_true',
      help='Save snapshot to gcs cloud rather than writing to stdout')

  # Usage:  download-stats map downloads.*
  map_parser = subparsers.add_parser('map', help='categorize the data')
  map_parser.add_argument(
      'files', nargs=argparse.REMAINDER, help='raw data files')

  args = parser.parse_args()
  if not args.command:
    parser.print_usage()
    sys.exit(1)

  if args.command == 'update':
    storage_bucket = None
    if args.save_cloud:
      storage_client = storage.Client()
      storage_bucket = storage_client.get_bucket(args.bucket)

    repos = DEFAULT_REPOS
    if args.all:
      repos = github.fetch_repos('bazelbuild')
    if args.repo_list_file:
      with open(args.repo_list_file, 'r') as rf:
        repos = [l.strip() for l in rf.read().strip().split('\n')]
    FetchDownloadCounts(repos, storage_bucket, args.folder)
  elif args.command == 'map':
    MapRawData(args.files)
  else:
    parser.print_usage()


if __name__ == '__main__':
  main()
