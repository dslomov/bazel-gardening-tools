#!/usr/bin/env python3

import collections
import datetime
import itertools

import database

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


def category_labels(labels):
    for l in labels:
        name = l["name"]
        if name.startswith("category:"):
            yield name


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


def make_console_printer(
        show_age=False,
        show_number=True,
        show_url=True,
        show_title=False,
        show_teams=False):
    """A customizable console printer."""

    def truncate(string, length):
        return string[:length] + ".." if len(string) > length else string

    def printer(issue):
        output = []

        if show_age:
            output.append(("{: <4}", latest_update_days_ago(issue)))
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
        predicate=lambda issue: is_open(issue) and not (
            has_team_label(issue) or has_label(issue, 'release')),
        printer=make_console_printer(show_title=True),
    )


def issues_with_category(reporter, issues):
    c_groups = collections.defaultdict(list)
    predicate = lambda issue: is_open(issue) and not (
        has_team_label(issue) or has_label(issue, "release"))
    for issue in filter(predicate, issues):
        categories = category_labels(issue["labels"])
        if not categories:
            categories = ["uncategorized"]
        for c in categories:
            c_groups[c].append(issue)

    for category in c_groups.keys():
       # print("------------------------")
       # print("Category: %s (%d issues)" % (category, len(c_groups[category])))
       for issue in c_groups[category]:
           print("%s|%s|%d|%s" % (
               category,
               issue_url(issue),
               latest_update_days_ago(issue),
               issue["title"]))


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


_REPORTS = {
    "more_than_one_team":
        lambda issues: more_than_one_team(print_report, issues),
    "issues_without_team":
        lambda issues: issues_without_team(print_report, issues),
    "triaged_no_priority":
        lambda issues: have_team_no_untriaged_no_priority(
            print_report_group_by_team, issues),
    "unmigrated":
        lambda issues: issues_with_category(print_report, issues),
}
        

def Report(which_reports):
    issues = database.GetIssues()
    for r in which_reports:
        _REPORTS[r](issues)


def ReportNames():
    return _REPORTS.keys()


#
# Gardening
#

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
        printer=make_console_printer(
            show_age=True, show_number=False, show_title=True))


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


def Garden(list_issues, list_pull_requests, stale_for_days):
    # We are only gardening open issues
    issues = database.GetIssues(is_open)
    if list_issues:
        issues_to_garden(print_report, issues, stale_for_days)
    if list_pull_requests:
        pull_requests_to_garden(print_report, issues, stale_for_days)
