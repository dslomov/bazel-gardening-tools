#! /usr/bin/env python3

import datetime
import argparse
import itertools
import json
import urllib.request

secrets = json.load(open("secrets.json"))
client_id = secrets["client_id"]
client_secret = secrets["client_secret"]

all_open_issues_file = "all-open-issues.json"
all_labels_file = "all-labels.json"


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


def fetch_issues(query):
    url = 'https://api.github.com/repos/bazelbuild/bazel/issues?client_id=' + client_id + '&client_secret=' + client_secret + '&per_page=100&' + query
    result = dict()
    while url:
        print(url)
        response = urllib.request.urlopen(url)
        issues = json.loads(response.read())
        for issue in issues:
            result[issue["number"]] = issue
        url = get_next_url(response.info())
    print(len(result))
    return list(result.values())


def dump_all_open_issues():
    issues = fetch_issues("q=is:open")
    json.dump(issues, open(all_open_issues_file, "w+"), indent=2)


def dump_labels():
    labels = []
    url = 'https://api.github.com/repos/bazelbuild/bazel/labels?client_id=' + client_id + '&client_secret=' + client_secret
    while url:
        print(url)
        response = urllib.request.urlopen(url)
        ls = json.loads(response.read())
        labels += ls
        url = get_next_url(response.info())
    json.dump(labels, open(all_labels_file, "w+"), indent=2)


def update():
    dump_all_open_issues()
    dump_labels()


#
# Helpers
#


# GitHub API datetime-stamps are already in UTC / Zulu time (+0000)
def parse_datetime(datetime_string):
    return datetime.datetime.strptime(datetime_string, "%Y-%m-%dT%H:%M:%SZ")


def issue_url(issue):
    return "https://github.com/bazelbuild/bazel/issues/" + str(issue["number"])


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
    return has_any_of_labels(issue, ["P0", "P1", "P2", "P3"])


def teams(issue):
    return map(lambda i: i["name"], team_labels(issue["labels"]))


def latest_update_days_ago(issue):
    return (datetime.datetime.now() - parse_datetime(issue["updated_at"])).days


def is_stale(issue, days_ago):
    return latest_update_days_ago(issue) >= days_ago


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


def issues_without_team(reporter, issues):
    reporter(
        issues,
        header="Open issues not assigned to any team",
        predicate=lambda issue: not has_team_label(issue),
        printer=lambda issue: "%s: %s" % (issue["number"], issue_url(issue)),
    )


def more_than_one_team(reporter, issues):
    def predicate(issue):
        return len(list(teams(issue))) > 1

    def printer(issue):
        n = issue["number"]
        return "%s: %s %s" % (n, ",".join(teams(issue)), issue_url(issue))

    reporter(
        issues,
        header="Issues assigned to more than one team:",
        predicate=predicate,
        printer=printer)


def have_team_no_untriaged_no_priority(reporter, issues):
    reporter(
        issues,
        header="Triaged issues without priority",
        predicate=lambda issue: has_team_label(issue) and not has_label(
            issue, "untriaged") and not has_priority(issue),
        printer=lambda issue: "%s: %s (%s)" % (issue["number"], issue_url(
            issue), ",".join(teams(issue))))


def issues_to_garden(reporter, issues, stale_for_days):
    def predicate(issue):
        return \
            not has_team_label(issue) \
            and not issue["assignee"] \
            and not is_pull_request(issue) \
            and is_stale(issue, stale_for_days)

    reporter(
        issues,
        header="Open issues not assigned to any team or person",
        predicate=predicate,
        printer=lambda issue: "%s: %s" % (issue["number"], issue_url(issue)))


def pull_requests_to_garden(reporter, issues, stale_for_days):
    def predicate(issue):
        return \
            not has_team_label(issue) \
            and not issue["assignee"] \
            and is_pull_request(issue) \
            and is_stale(issue, stale_for_days)

    reporter(
        issues,
        header="Open pull requests not assigned to any team or person",
        predicate=predicate,
        printer=lambda issue: "%s: %s" % (issue["number"], issue_url(issue)))


def report(which_reports):
    issues = json.load(open(all_open_issues_file))
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
    issues = json.load(open(all_open_issues_file))
    if list_issues:
        issues_to_garden(print_report, issues, stale_for_days)
    if list_pull_requests:
        pull_requests_to_garden(print_report, issues, stale_for_days)


def main():
    parser = argparse.ArgumentParser(
        description="Gather Bazel's issues and pull requests data")
    subparsers = parser.add_subparsers(dest="command", help="select a command")

    subparsers.add_parser("update", help="update the datasets")

    report_parser = subparsers.add_parser(
        "report", help="generate a full report")

    garden_parser = subparsers.add_parser(
        "garden",
        help="generate issues/pull requests that need gardening attention")
    garden_parser.add_argument(
        '-i',
        '--list_issues',
        default=True,
        type=lambda x: (str(x).lower() == 'true'),
        help="list issues that need attention (true/false)")
    garden_parser.add_argument(
        '-p',
        '--list_pull_requests',
        default=True,
        type=lambda x: (str(x).lower() == 'true'),
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
        update()
    elif args.command == "report":
        report(list(reports.keys()) if args.all_reports else args.report)
    elif args.command == "garden":
        garden(args.list_issues, args.list_pull_requests, args.stale_for_days)
    else:
        parser.print_usage()


main()
