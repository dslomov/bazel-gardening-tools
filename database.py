#! /usr/bin/env python3

import collections
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


#
# Label helpers
#

PRIMARY_LABEL_DB = 'labels.bazel.json'

Label = collections.namedtuple('Label', ['key', 'name', 'color', 'url'])

class LabelDB(object):
  """LabelsDB implements a collection of labels.

  The intent is that the color choices for main repo win over those in the
  secondary ones. To accomplish that we preload the labels from the main
  repo and add new ones lazily as we encounter them.
  """

  def __init__(self, db_file):
    self.key_to_label = {}
    self._load(db_file)

  def _load(self, db_file):
    try:
      with open(db_file, 'r') as dbf:
        labels = json.load(dbf)
        for label in labels:
          self._insert(label)
    except FileNotFoundError:
      pass

  def _insert(self, label):
    """Inserts a new label from the raw json struct."""
    name = label['name']
    key = self._normalize(name)
    label = Label(
        key=key,
        name=name,
        color=label['color'],
        url=label['url'],
    )
    self.key_to_label[key] = label
    return label

  @staticmethod
  def _normalize(name):
    """The compare key for labels is alphanumeric only, with no punctuation.
    
    This accounts for minor punctuation differences between projects.
    """
    return ''.join(filter(lambda ch: ch.isalnum(), name.lower()))

  def get(self, label):
    """Gets the Label struct for a given label name.

    Args:
      label: a label name. If the name is not in the database, a new Label
          object is created and that is returned.
    """
    key = self._normalize(label['name'])
    ret = self.key_to_label.get(key)
    if not ret:
      ret = self._insert(label)
    return ret

  def all(self):
    return self.key_to_label.values()


# export the singleton
label_db = LabelDB(PRIMARY_LABEL_DB)
