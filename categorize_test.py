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
          self.assertEqual(product, buckets.product, str(buckets))
          self.assertEqual(version, buckets.version, str(buckets))
          self.assertEqual(arch, str(buckets.arch), str(buckets))
          self.assertEqual(os, str(buckets.os), str(buckets))
          self.assertEqual(packaging, str(buckets.packaging), str(buckets))
          self.assertEqual(installer, buckets.installer, str(buckets))
          self.assertEqual(is_bin, str(buckets.is_bin), str(buckets))
          self.assertEqual(
              rest,
              '{%s}%s' % (buckets.attributes, buckets.leftover),
              str(buckets))


if __name__ == '__main__':
  unittest.main()
