#!/usr/bin/env python3

import collections
import re
import string
import sys

# The bins we categorize artifacts as
Bins = collections.namedtuple(
    'Bins',
    'product version arch os packaging installer is_bin attributes leftover')

# rules_go-0.10.0.tar.gz
_PRODUCT_VERSION_RE = re.compile(r'(\w+[-\w]*)[-_.]v?(\d+\.\d+\.\d+[a-z\d]*)[^.\D]?')
#  bazel-toolchains-0dc4917.tar.gz
_PRODUCT_GITHASH_RE = re.compile(r'(\w+[-\w]*)[-_.]([0-9a-f]{7})')
_VERSION_RE = re.compile(r'[-_.]v?(\d+\.\d+\.\d+[a-z\d]*(-rc\d+)?)|(\d+\.\d+[a-z\d]*(-rc\d+)?)')
_JDK_SPEC_RE = re.compile(r'[^a-z]?(jdk\d*)')

_LINUX_PACKAGE_EXTENSIONS = ['.sh', '.deb', '.rpm', '.zip', '.tar.gz', '.tgz']
_MACOS_PACKAGE_EXTENSIONS = ['.dmg', '.mac', '.osx']
_WINDOWS_PACKAGE_EXTENSIONS = ['.exe']

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
    m = _PRODUCT_GITHASH_RE.match(todo)
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
