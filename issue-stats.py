#! /usr/bin/env python3

import datetime
import argparse
import itertools
import json
import os
import urllib.request
import ssl

ssl._create_default_https_context = ssl._create_unverified_context
secrets = json.load(open("secrets.json"))
client_id = secrets["client_id"]
client_secret = secrets["client_secret"]

all_issues_file = "all-issues.json"
all_labels_file = "all-labels.json"


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
        'per_page=100',
    ]
    if query:
        query_args.append(query)
    if modified_after:
        query_args.append('since=%s' % datetime.datetime.utcfromtimestamp(
            modified_after).strftime('%Y-%m-%dT%H:%M:%SZ'))
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
        # Notice the hackery. We ask for 10 minutes before the mod time so we
        # pick up issues that were modified *during* the last time we queried.
        # We could do better by finding the highest mod time in the database.
        db_time = os.path.getmtime(all_issues_file) - 600
        with open(all_issues_file) as issues_db:
            issues = json.load(issues_db)
        url_to_issue = {}
        for issue_index in range(len(issues)):
            issue  = issues[issue_index]
            url_to_issue[issue_url(issue)] = issue_index
    for repo in REPOS:
        new_issues = fetch_issues(repo, "", modified_after=db_time)
        if full_update:
            issues.extend(new_issues)
        else:
            for issue in new_issues:
                url = issue_url(issue)
                if url in url_to_issue:
                    print("updating %s" % url)
                    issues[url_to_issue.get(url)] = issue
                else:
                    print("new issue %s" % url)
                    issues.append(issue)
    json.dump(issues, open(all_issues_file, "w+"), indent=2)
    for repo in REPOS:
        dump_labels(repo)



#
# Helpers
#


# GitHub API datetime-stamps are already in UTC / Zulu time (+0000)
def parse_datetime(datetime_string):
    return datetime.datetime.strptime(datetime_string, "%Y-%m-%dT%H:%M:%SZ")


def issue_url(issue):
    return issue["html_url"]


def team_labels(labels):
    for l in labels:
        if l["name"].startswith("team-"):
            yield l


def all_teams(labels):
    for team_label in team_labels(labels):
        yield team_label["name"]


#
# Issue predicates
#
def is_open(issue):
    return issue["state"] == "open"

def has_team_label(issue):
    for _ in team_labels(issue["labels"]):
        return True
    return False


def is_pull_request(issue):
    return "pull_request" in issue


def has_label(issue, label):
    for l in issue["labels"]:
        if l["name"] == label:
            return True
    return False


def has_any_of_labels(issue, labels):
    for l in issue["labels"]:
        if l["name"] in labels:
            return True
    return False


def has_priority(issue):
    return has_any_of_labels(issue, ["P0", "P1", "P2", "P3", "P4"])


def needs_more_data(issue):
    return has_label(issue, "more data needed")


def work_in_progress(issue):
    return has_label(issue, "WIP")


def teams(issue):
    return map(lambda i: i["name"], team_labels(issue["labels"]))


def latest_update_days_ago(issue):
    return (datetime.datetime.now() - parse_datetime(issue["updated_at"])).days


def is_stale(issue, days_ago):
    return latest_update_days_ago(issue) >= days_ago


def has_cla(issue):
    return has_label(issue, "cla: yes")


#
# Reports
#


def print_report(issues, header, predicate, printer):
    print(header)
    count = 0
    for issue in issues:
        if predicate(issue):
            count = count + 1
            print(printer(issue))
    print("%d issues" % count)
    print("---------------------------")


def print_report_group_by_team(issues, header, predicate, printer):
    def teamof(issue):
        t = list(teams(issue))
        if len(t) == 0:
            return "<No team>"
        else:
            return t[0]

    print(header)
    sorted_issues = sorted(filter(predicate, issues), key=teamof)
    for team, issues in itertools.groupby(sorted_issues, teamof):
        print("%s:" % team)
        for issue in issues:
            print(printer(issue))
    print("---------------------------")


def make_console_printer(show_number=True,
                         show_url=True,
                         show_title=False,
                         show_teams=False):
    """A customizable console printer."""

    def truncate(string, length):
        return string[:length] + ".." if len(string) > length else string

    def printer(issue):
        output = []

        if show_number:
            output.append(("{: <4}", issue["number"]))
        if show_url:
            output.append(("{: <47}", issue_url(issue)))
        if show_title:
            output.append(("{: <50}", truncate(issue["title"], 48)))
        if show_teams:
            output.append(("{: <30}", truncate(",".join(teams(issue)), 28)))

        return " | ".join([parts[0] for parts in output
                           ]).format(*[parts[1] for parts in output])

    return printer


def issues_without_team(reporter, issues):
    reporter(
        issues,
        header="Open issues not assigned to any team",
        predicate=lambda issue: is_open(issue) and not has_team_label(issue),
        printer=make_console_printer(show_title=True),
    )


def more_than_one_team(reporter, issues):
    def predicate(issue):
        return is_open(issue) and len(list(teams(issue))) > 1

    reporter(
        issues,
        header="Issues assigned to more than one team:",
        predicate=predicate,
        printer=make_console_printer(show_teams=True))


def have_team_no_untriaged_no_priority(reporter, issues):
    reporter(
        issues,
        header="Triaged issues without priority",
        predicate=lambda issue: is_open(issue)
                                and has_team_label(issue)
                                and not has_label(issue, "untriaged")
                                and not has_priority(issue)
                                and not needs_more_data(issue)
                                and not is_pull_request(issue),
        printer=make_console_printer(show_teams=True))


def issues_to_garden(reporter, issues, stale_for_days):
    def predicate(issue):
        return \
            not has_team_label(issue) \
            and not issue["assignee"] \
            and not is_pull_request(issue) \
            and is_stale(issue, stale_for_days) \
            and not work_in_progress(issue)

    reporter(
        issues,
        header="Open issues not assigned to any team or person",
        predicate=predicate,
        printer=make_console_printer(show_title=True))


def pull_requests_to_garden(reporter, issues, stale_for_days):
    def predicate(issue):
        return \
            not has_team_label(issue) \
            and not issue["assignee"] \
            and is_pull_request(issue) \
            and is_stale(issue, stale_for_days) \
            and not work_in_progress(issue) \
            and has_cla(issue)

    reporter(
        issues,
        header="Open pull requests not assigned to any team or person",
        predicate=predicate,
        printer=make_console_printer(show_title=True))


def report(which_reports):
    issues = json.load(open(all_issues_file))
    for r in which_reports:
        reports[r](issues)


reports = {
    "more_than_one_team":
    lambda issues: more_than_one_team(print_report, issues),
    "issues_without_team":
    lambda issues: issues_without_team(print_report, issues),
    "triaged_no_priority":
    lambda issues: have_team_no_untriaged_no_priority(
        print_report_group_by_team, issues)
}


def garden(list_issues, list_pull_requests, stale_for_days):
    # We are only gardening open issues
    issues = filter(is_open, json.load(open(all_issues_file)))
    if list_issues:
        issues_to_garden(print_report, issues, stale_for_days)
    if list_pull_requests:
        pull_requests_to_garden(print_report, issues, stale_for_days)


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
        choices=list(reports.keys()),
        help="show selected report (multiple values possible)")
    args = parser.parse_args()

    if args.command == "update":
        update(args.full)
    elif args.command == "report":
        report(args.report if args.report else list(reports.keys()))
    elif args.command == "garden":
        garden(args.list_issues, args.list_pull_requests, args.stale_for_days)
    else:
        parser.print_usage()


main()
