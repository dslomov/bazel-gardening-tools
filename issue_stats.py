#! /usr/bin/env python3

import argparse
import json

import database
import github
import reports


DEFAULT_REPOS = [
  'bazelbuild/apple_support',
  'bazelbuild/bazel',
  'bazelbuild/bazel-blog',
  'bazelbuild/bazel-federation',
  'bazelbuild/bazel-skylib',
  'bazelbuild/bazel-toolchains',
  'bazelbuild/bazel-website',
  'bazelbuild/buildtools',
  'bazelbuild/codelabs',
  'bazelbuild/examples',
  'bazelbuild/intellij',
  'bazelbuild/skydoc',
  'bazelbuild/starlark',
]


def label_file_for_repo(repo):
    repo_basename = repo.split('/')[-1]
    return 'labels.%s.json' % repo_basename


def update_labels(repo):
    labels = github.fetch_labels(repo)
    repo_basename = repo.split('/')[-1]
    json.dump(labels, open(label_file_for_repo(repo), "w+"), indent=2)


def build_issue_index(issues, reset_repos):
    # Find the most recent issue per repo so we can do incremental update
    # for different repos in each run.
    repo_to_latest = {}
    url_to_issue = {}
    for issue_index, issue in enumerate(issues):
        url_to_issue[issue['url']] = issue_index
        dt = database.update_time(issue)
        repo = '/'.join(issue['repository_url'].split('/')[-2:])
        latest_change = repo_to_latest.get(repo) or None
        if latest_change == None or latest_change < dt:
            repo_to_latest[repo] = dt
    db_time = latest_change.timestamp()
    for repo in reset_repos or []:
      repo_to_latest[repo] = None
    return url_to_issue, repo_to_latest


def update(repos, full_update=False, reset_repos=None, verbose=False):
    # Find the most recent issue per repo so we can do incremental update
    # for different repos in each run.
    if full_update:
        issues = []
        url_to_issue = {}
        repo_to_latest = {}
    else:
        with open(database.all_issues_file) as issues_db:
            issues = json.load(issues_db)
        url_to_issue, repo_to_latest = build_issue_index(issues, reset_repos)

    for repo in repos:
        db_time = repo_to_latest.get(repo) or None
        if db_time:
            db_time = db_time.timestamp()
        if verbose:
            print("Getting issues for", repo, "after", str(db_time))
        try:
            new_issues = github.fetch_issues(repo, "", modified_after=db_time,
                                             verbose=verbose)
        except:
            continue

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
    for repo in repos:
        if verbose:
            print("Getting labels for ", repo)
        update_labels(repo)


def main():
    parser = argparse.ArgumentParser(
        description="Gather Bazel's issues and pull requests data")
    parser.add_argument(
        '--user_list_file',
        help='File of github handles used to filter reports by user.')

    parser.add_argument('--verbose', action='store_true',
                        help='Be more verbose')

    subparsers = parser.add_subparsers(dest="command", help="select a command")

    update_parser = subparsers.add_parser("update", help="update the datasets")
    update_parser.add_argument(
        "--full", action='store_true',
        help="Do a full rather than incremental update")
    update_parser.add_argument(
        '--repo', action='append',
        help='Repository to do an update for. May be repeated.')
    update_parser.add_argument(
        '--repo_list_file', action='store',
        help='Get repositories listed in this file')
    update_parser.add_argument(
        '--reset_repo', action='append',
        help='Specific repository to do a full update for. May be repeated')

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

    html_parser = subparsers.add_parser(
        "html", help="generate HTML for issues/pull requests that need attention")

    report_parser = subparsers.add_parser(
        "report", help="generate a full report")
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
        choices=reports.report_names(),
        help="show selected report (multiple values possible)")

    args = parser.parse_args()
    user_list = None
    if args.user_list_file:
      with open(args.user_list_file, 'r') as inp:
        user_list = [x.strip() for x in inp.read().split('\n')]
    if args.command == "update":
        repos = DEFAULT_REPOS
        if args.repo:
          repos = args.repo
        elif args.repo_list_file:
          with open(args.repo_list_file, 'r') as rf:
            repos = [l.strip() for l in rf.read().strip().split('\n')]
        update(repos, args.full, args.reset_repo, args.verbose)
    elif args.command == "report":
        reports.report(args.report if args.report else reports.report_names(),
                       user_list=user_list)
    elif args.command == "garden":
        reports.garden(args.list_issues, args.list_pull_requests, args.stale_for_days)
    elif args.command == "html":
        reports.html_garden()
    else:
        parser.print_usage()


if __name__ == '__main__':
  main()
