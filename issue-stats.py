#! /usr/bin/env python

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import argparse

import sys, json, urllib2

secrets = json.load(open("secrets.json"))
client_id = secrets["client_id"]
client_secret = secrets["client_secret"]

all_open_issues_file = "all-open-issues.json"
all_labels_file = "all-labels.json"


def load_json(url):
    response = urllib2.urlopen(url).read()
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
    start_at = 0
    url = 'https://api.github.com/repos/bazelbuild/bazel/issues?client_id=' + client_id + '&client_secret=' + client_secret + '&per_page=100&' + query
    result = dict()
    while url != None:
        print(url)
        response = urllib2.urlopen(url)
        issues = json.loads(response.read())
        for issue in issues:
            result[issue["number"]] = issue
        url = get_next_url(response.info())
    print(len(result))
    return result.values()


def dump_all_open_issues():
    issues = fetch_issues("q=is:issue&is:open")
    json.dump(issues, open(all_open_issues_file, "w+"), indent=2)


def dump_labels():
    labels = []
    url = 'https://api.github.com/repos/bazelbuild/bazel/labels?client_id=' + client_id + '&client_secret=' + client_secret
    while url:
        print(url)
        response = urllib2.urlopen(url)
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
def issue_url(issue):
    return "https://github.com/bazelbuild/bazel/issues/" + str(issue["number"])


def team_labels(labels):
    for l in labels:
        if l["name"].startswith("team-"):
            yield l


def all_teams(labels):
    teams = []
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


def issues_without_team(issues):
    print_report(
        issues,
        header="Open issues not assigned to any team",
        predicate=lambda (issue): not has_team_label(issue),
        printer=lambda (issue): "%s: %s" % (issue["number"], issue_url(issue)),
    )


def more_than_one_team(issues):
    def predicate(issue):
        return len(teams(issue)) > 1

    def printer(issue):
        n = issue["number"]
        return "%s: %s %s" % (n, ",".join(teams(issue)), issue_url(issue))

    print_report(
        issues,
        header="Issues assigned to more than one team:",
        predicate=predicate,
        printer=printer)


def have_team_no_untriaged_no_priority(issues):
    print_report(issues,
      header = "Triaged issues without priority",
                 predicate = lambda(issue): has_team_label(issue) and not has_label(issue, "untriaged") and not has_priority(issue),
                 printer = lambda(issue): "%s: %s (%s)" % (issue["number"], issue_url(issue), ",".join(teams(issue)))
    )


def issues_to_garden(issues):
    print_report(
        issues,
        header="Open issues not assigned to any team or person",
        predicate=
        lambda (issue): not has_team_label(issue) and not issue["assignee"] and not is_pull_request(issue),
        printer=lambda (issue): "%s: %s" % (issue["number"], issue_url(issue)))


def pull_requests_to_garden(issues):
    print_report(
        issues,
        header="Open issues not assigned to any team or person",
        predicate=
        lambda (issue): not has_team_label(issue) and not issue["assignee"] and not is_pull_request(issue),
        printer=lambda (issue): "%s: %s" % (issue["number"], issue_url(issue)))


def report():
    issues = json.load(open(all_open_issues_file))
    more_than_one_team(issues)
    issues_without_team(issues)
    have_team_no_untriaged_no_priority(issues)


def garden(list_issues, list_pull_requests):
    issues = json.load(open(all_open_issues_file))
    if list_issues:
        issues_to_garden(issues)
    if list_pull_requests:
        pull_requests_to_garden(issues)


def main():
    parser = argparse.ArgumentParser(
        description="Gather Bazel's issues and pull requests data")
    subparsers = parser.add_subparsers(dest="command", help="select a command")

    update_parser = subparsers.add_parser("update", help="update the datasets")

    report_parser = subparsers.add_parser("report", help="generate a full report")

    garden_parser = subparsers.add_parser("garden", help="generate issues/pull requests that need gardening attention")
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
    args = parser.parse_args()

    if args.command == "update":
        update()
    elif args.command == "report":
        report()
    elif args.command == "garden":
        garden(args.list_issues, args.list_pull_requests)


main()
