#! /usr/bin/env python3

import json

all_issues_file = "all-issues.json"


def GetIssues(predicate=None):
    issues = json.load(open(all_issues_file))
    if predicate:
        return filter(predicate, issues)
    return issues
