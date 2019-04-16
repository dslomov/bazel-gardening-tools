#! /usr/bin/env python3

import argparse
import json

import database
import github
import reports


REPOS = [
  'bazelbuild/starlark',
  'bazelbuild/bazel-website',
  'bazelbuild/bazel-skylib',
  'bazelbuild/bazel',
]


def label_file_for_repo(repo):
    repo_basename = repo.split('/')[-1]
    return 'labels.%s.json' % repo_basename


def update_labels(repo):
    labels = github.fetch_labels(repo)
    repo_basename = repo.split('/')[-1]
    json.dump(labels, open(label_file_for_repo(repo), "w+"), indent=2)


def update(full_update=False):
    if full_update:
        db_time = None
        issues = []
    else:
        with open(database.all_issues_file) as issues_db:
            issues = json.load(issues_db)
        url_to_issue = {}
        latest_change = None
        for issue_index in range(len(issues)):
            issue  = issues[issue_index]
            url_to_issue[issue['url']] = issue_index
            dt = database.update_time(issue)
            if latest_change == None or latest_change < dt:
                latest_change = dt
        db_time = latest_change.timestamp()

    for repo in REPOS:
        new_issues = github.fetch_issues(repo, "", modified_after=db_time)
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
        update_labels(repo)


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
