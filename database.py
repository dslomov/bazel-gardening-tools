#! /usr/bin/env python3

import datetime
import json

all_issues_file = 'all-issues.json'


# GitHub API datetime-stamps are already in UTC / Zulu time (+0000)
def parse_datetime(datetime_string):
  return datetime.datetime.strptime(datetime_string, '%Y-%m-%dT%H:%M:%SZ')


def get_issues(predicate=None):
  issues = json.load(open(all_issues_file))
  if predicate:
    return filter(predicate, issues)
  return issues


#
# issue helpers
#

def update_time(issue):
  return parse_datetime(issue['updated_at'])


def created_by(issue):
  """Returns the user of the issue creator."""
  return User(issue.get('user'))


class User(object):

   def __init__(self, json):
     self.data = json

   @property
   def name(self):
     return self.data['login']

   @property
   def link(self):
     return self.data['html_url']
