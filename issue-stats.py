#! /usr/bin/env python3

import datetime
import argparse
import itertools
import json
import os
import urllib.request
import ssl

import database
import reports

ssl._create_default_https_context = ssl._create_unverified_context
secrets = json.load(open("secrets.json"))
client_id = secrets["client_id"]
client_secret = secrets["client_secret"]


REPOS = [
  'bazelbuild/starlark',
  'bazelbuild/bazel-website',
  'bazelbuild/bazel-skylib',
  'bazelbuild/bazel',
]

GITHUB_API_URL_BASE = 'https://api.github.com/repos/'


def add_client_secret(url):
    sep = '&'
    if not '?' in url:
        sep = '?'
    return url + sep + 'client_id=' + client_id + '&client_secret=' + client_secret


def load_json(url):
    response = urllib.request.urlopen(url).read()
    return json.loads(response)


def get_next_url(response):
    if "Link" not in response:
        return None
    link_header = response["Link"]
    links = link_header.split(",")
    for link_segment in links:
        if link_segment.find("rel=\"next\"") == -1:
            continue
        link = link_segment[link_segment.index('<') +
                            1:link_segment.index('>')]
        return link
    return None


def fetch_issues(repo, query, modified_after=None):
    """Fetches issues from a repo.

    Args:
      repo: (str) '<organization>/<repo>'
      query: (str) optional query
      modified_after: (float) only fetch issues modified after this (UTC) time.
    """
    query_args = [
        'state=all',  # needed to get closed issues
        'per_page=100',
    ]
    if query:
        query_args.append(query)
    if modified_after:
        utc_time_s = datetime.datetime.utcfromtimestamp(
            modified_after).strftime('%Y-%m-%dT%H:%M:%SZ')
        query_args.append('since=%s' % utc_time_s)
        print('Fecthing issues changed since: %s' % utc_time_s)
    url = GITHUB_API_URL_BASE + repo + '/issues?' + '&'.join(query_args)
    result = dict()
    i = 0
    while url:
        print(url)
        response = urllib.request.urlopen(add_client_secret(url))
        issues = json.loads(response.read())
        for issue in issues:
            result[issue["number"]] = issue
        url = get_next_url(response.info())
    print(len(result))
    return list(result.values())


def label_file_for_repo(repo):
    repo_basename = repo.split('/')[-1]
    return 'labels.%s.json' % repo_basename


def dump_labels(repo):
    labels = []
    url = GITHUB_API_URL_BASE + repo + '/labels'
    while url:
        print(url)
        response = urllib.request.urlopen(add_client_secret(url))
        ls = json.loads(response.read())
        labels += ls
        url = get_next_url(response.info())
    repo_basename = repo.split('/')[-1]
    json.dump(labels, open(label_file_for_repo(repo), "w+"), indent=2)


def update(full_update=False):
    if full_update:
        db_time = None
        issues = []
    else:
        with open(all_issues_file) as issues_db:
            issues = json.load(issues_db)
        url_to_issue = {}
        latest_change = None
        for issue_index in range(len(issues)):
            issue  = issues[issue_index]
            url_to_issue[issue['url']] = issue_index
            dt = parse_datetime(issue["updated_at"])
            if latest_change == None or latest_change < dt:
                latest_change = dt
        db_time = latest_change.timestamp()

    for repo in REPOS:
        new_issues = fetch_issues(repo, "", modified_after=db_time)
        if full_update:
            issues.extend(new_issues)
        else:
            for issue in new_issues:
                url = issue['url']
                if url in url_to_issue:
                    print("updating %s" % url)
                    issues[url_to_issue.get(url)] = issue
                else:
                    print("new issue %s" % url)
                    issues.append(issue)
    json.dump(issues, open(database.all_issues_file, "w+"), indent=2)
    for repo in REPOS:
        dump_labels(repo)


def main():
    parser = argparse.ArgumentParser(
        description="Gather Bazel's issues and pull requests data")
    subparsers = parser.add_subparsers(dest="command", help="select a command")

    update_parser = subparsers.add_parser("update", help="update the datasets")
    update_parser.add_argument(
        "--full", action='store_true',
        help="Do a full rather than incremental update")

    report_parser = subparsers.add_parser(
        "report", help="generate a full report")

    garden_parser = subparsers.add_parser(
        "garden",
        help="generate issues/pull requests that need gardening attention")
    garden_parser.add_argument(
        '-i',
        '--list_issues',
        action='store_true',
        help="list issues that need attention (true/false)")
    garden_parser.add_argument(
        '-p',
        '--list_pull_requests',
        action='store_true',
        help="list pull requests that need attention (true/false)")
    garden_parser.add_argument(
        '-s',
        '--stale_for_days',
        type=int,
        default=0,
        help=
        "list issues/prs that have not been updated for more than the specified number of days (number, default is 0)"
    )

    report_selector = report_parser.add_mutually_exclusive_group()
    report_selector.add_argument(
        '-a',
        '--all',
        action="store_true",
        dest="all_reports",
        help="show all reports")
    report_selector.add_argument(
        "-r",
        "--report",
        action="append",
        choices=reports.ReportNames(),
        help="show selected report (multiple values possible)")
    args = parser.parse_args()

    if args.command == "update":
        update(args.full)
    elif args.command == "report":
        reports.Report(args.report if args.report else reports.ReportNames())
    elif args.command == "garden":
        reports.Garden(args.list_issues, args.list_pull_requests, args.stale_for_days)
    else:
        parser.print_usage()


main()
