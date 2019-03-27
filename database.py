#! /usr/bin/env python3

import datetime
import json

all_issues_file = 'all-issues.json'


# GitHub API datetime-stamps are already in UTC / Zulu time (+0000)
def parse_datetime(datetime_string):
    return datetime.datetime.strptime(datetime_string, '%Y-%m-%dT%H:%M:%SZ')


def GetIssues(predicate=None):
    issues = json.load(open(all_issues_file))
    if predicate:
        return filter(predicate, issues)
    return issues


def UpdateTime(issue):
    return parse_datetime(issue['updated_at'])
