#!/usr/bin/env python3
"""Tests for categorize."""

import re
import unittest

import categorize


class CategorizeTest(unittest.TestCase):

  version_re = re.compile(
      r'[-_.]v?(\d+\.\d+\.\d+[a-z\d]*(-rc\d+)?)|(\d+\.\d+[a-z\d]*(-rc\d+)?)')

  def test_samples(self):
    with open('testdata/categorize_samples.txt', 'r') as samples:
      for sample in samples:
        (file, product, version, arch, os, packaging, installer, is_bin,
         rest) = sample.strip().split('|')
        with self.subTest(file=file):
          m = self.version_re.search(file)
          # Only use the default version if we can not find the common version
          # pattern in the filename.
          if m:
            buckets = categorize.Categorize(file)
          else:
            buckets = categorize.Categorize(file,
                                            default_version=version)
          self.assertEqual(product, buckets.product)
          self.assertEqual(version, buckets.version)
          self.assertEqual(arch, str(buckets.arch))
          self.assertEqual(os, str(buckets.os))
          self.assertEqual(packaging, str(buckets.packaging))
          self.assertEqual(installer, buckets.installer)
          self.assertEqual(is_bin, str(buckets.is_bin))
          self.assertEqual(rest, '{%s}%s' % (buckets.attributes,
                                             buckets.leftover))


if __name__ == '__main__':
  unittest.main()
