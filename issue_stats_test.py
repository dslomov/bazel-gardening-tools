#!/usr/bin/env python3
"""Tests for issue-stats.py."""

import json
import unittest

import issue_stats

class IssueStatsTest(unittest.TestCase):

  def setUp(self):
    # This is just a frozen copy of a database sample as of 2019-08-23. If you
    # update it by taking a new sample, You will have to adjust the counts.
    with open('testdata/issue_db.json', 'r') as issues_db:
      self.issues = json.load(issues_db)

  def test_build_issue_index(self):
    url_to_issue, repo_to_latest = issue_stats.build_issue_index(
        self.issues, [])

    self.assertEqual(len(url_to_issue), 11609)
    self.assertEqual(len(repo_to_latest), 32)
    self.assertEqual(len([date for date in repo_to_latest.values() if date]),
                     32)

  def test_build_issue_index_with_reset(self):
    url_to_issue, repo_to_latest = issue_stats.build_issue_index(
        self.issues, ['bazelbuild/starlark', 'bazelbuild/buildtools'])

    self.assertEqual(len(url_to_issue), 11609)
    self.assertEqual(len(repo_to_latest), 32)
    self.assertEqual(len([date for date in repo_to_latest.values() if date]),
                     30)


if __name__ == '__main__':
  unittest.main()
