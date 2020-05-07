#!/usr/bin/env python3

import collections
import datetime
import itertools
import re

import database
import html_writer


CAT_2_TEAM = {
    'category: BEP': 'team-Remote-Exec',
    'category: correctness / reproducibility': 'team-Configurability',
    'category: extensibility > toolchains': 'team-Configurability',
    'category: local execution / caching': 'team-Local-Exec',
    'category: misc > misc': 'team-Product',
    'category: misc > release / binary': 'team-Product',
    'category: misc > testing': 'team-Performance',
    'category: rules > java': 'team-Rules-Java',
    'category: rules > misc native': 'team-Rules-Server',
    'category: rules > ObjC / iOS / J2ObjC': 'team-Apple',
    'category: sandboxing': 'team-Local-Exec',
    'category: skylark > pkg build defs': 'team-Rules-Server',
}

#
# Helpers
#

# Look for WIP markers in issue titles
_WIP_RE = re.compile(r'\bwip:?\b')


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


def get_any_of_labels(issue, labels):
    for l in issue["labels"]:
        if l["name"] in labels:
            return l
    return None


def has_priority(issue):
    return get_priority(issue) != None

def get_priority(issue):
    return get_any_of_labels(issue, ["P0", "P1", "P2", "P3", "P4"])

def needs_more_data(issue):
    return has_label(issue, "more data needed")


def work_in_progress(issue):
    return has_label(issue, "WIP") or _WIP_RE.search(issue["title"].lower())


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


def print_report(issues, header, predicate, printer, sort_keys=None):
    print(header)
    count = 0
    for issue in get_sorted_issues(issues, predicate, sort_keys):
        count = count + 1
        print(printer(issue))
    print("%d issues" % count)
    print("---------------------------")


def get_sorted_issues(issues, predicate, sort_keys):
    filtered = filter(predicate, issues)
    if not sort_keys:
        return filtered
    for key, rev in sort_keys:
        filtered = sorted(filtered, key=key, reverse=rev)
    return filtered


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
        show_author=False,
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
        if show_author:
            output.append(("{: <12}", issue["user"]["login"]))
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


def stale_pull_requests(reporter, issues, days):
    def predicate(issue):
        return (
            is_open(issue)
            and is_pull_request(issue)
            and is_stale(issue, days)
            and not work_in_progress(issue)
        )

    reporter(
        issues,
        header="Stale pull requests for %s days" % days,
        predicate=predicate,
        printer=make_console_printer(show_title=True, show_age=True))


def incompatible_flag_description(title):
    pos = title.find(": ")
    if pos >= 0:
      return title[0:pos], title[pos+2:]
    else:
      return "", title

def breaking_changes_1_0(reporter, issues):
    def predicate(issue):
        return has_label(issue, "breaking-change-1.0")
    def printer(issue):
        flag, desc = incompatible_flag_description(issue["title"])
        return "%s | %s" % (issue_url(issue), flag if flag else desc)
    reporter(
        issues,
        header="Breaking changes 1.0",
        predicate=predicate,
        printer=printer)


def pr_backlog(reporter, issues):
    def predicate(issue):
        return \
            is_open(issue) \
            and is_pull_request(issue) \
            and has_cla(issue) \
            and is_stale(issue, 30) \
            and not work_in_progress(issue)

    reporter(
        issues,
        header="age | pr | owner | url | title",
        predicate=predicate,
        printer=make_console_printer(
            show_age=True, show_number=True, show_author=True, show_title=True),
        sort_keys = [
            # TODO(aiuto): secondary sort first
            (lambda issue: latest_update_days_ago(issue), True),
            (lambda issue: issue["user"]["login"], False),
        ]
    )

def open_issues_by_repo(issues, labels=None):
    def predicate(issue):
      if not labels:
        return is_open(issue)
      return is_open(issue) and get_any_of_labels(issue, labels)

    repos = {}
    for issue in filter(predicate, issues):
      repo = issue['repository_url'].split('/')[-1:][0]
      if not repo in repos:
        repos[repo] = collections.defaultdict(int)
      repos[repo]['all'] += 1
      if get_any_of_labels(issue, ['documentation', 'type: documentation']):
        repos[repo]['docs'] += 1
      has_priority = False
      for priority in ('P0', 'P1', 'P2', 'P3', 'P4'):
        if has_label(issue, priority):
          repos[repo][priority] += 1
          has_priority = True
          break
      if not has_priority:
          repos[repo]['unprioritized'] += 1

    repo_names = sorted(repos.keys())
    today_label = datetime.datetime.now().strftime('%Y-%m-%d')
    print(today_label, 'all', ','.join('%s' % r for r in repo_names))
    print(today_label, 'all',
          ','.join('%d' % repos[r].get('all', 0) for r in repo_names))
    print(today_label, 'docs',
          ','.join('%d' % repos[r].get('docs', 0) for r in repo_names))
    for priority in ('P0', 'P1', 'P2', 'P3', 'P4', 'unprioritized'):
      print(today_label, priority,
            ','.join('%d' % repos[r].get(priority, 0) for r in repo_names))


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
    "stale_pull_requests_14d":
        lambda issues: stale_pull_requests(print_report, issues, 14),
    "breaking_changes_1.0":
        lambda issues: breaking_changes_1_0(print_report, issues),
    "team_pr_backlog":
        lambda issues: pr_backlog(print_report, issues),
    "open_issues_by_repo":
        lambda issues: open_issues_by_repo(issues),
    "open_doc_issues_by_repo":
    lambda issues: open_issues_by_repo(
        issues, labels=['documentation', 'type: documentation']),
}


def report(which_reports, user_list=None):
    pred = None
    if user_list:
        pred = lambda issue: issue["user"]["login"] in user_list
    issues = database.get_issues(predicate=pred)
    for r in which_reports:
       _REPORTS[r](issues)


def report_names():
    return _REPORTS.keys()


def label_html(label):
  """Returns html for rendering a Label."""
  return '<span class="label-%s">%s</span>' % (label.key, label.name)


def html_garden():
    issues = database.get_issues()
    c_groups = collections.defaultdict(list)
    predicate = lambda issue: is_open(issue) and not (
        has_team_label(issue) or has_label(issue, "release"))
    for issue in filter(predicate, issues):
        categories = category_labels(issue["labels"])
        if not categories:
            categories = ["uncategorized"]
        for c in categories:
            c_groups[c].append(issue)

    p = html_writer.HTMLWriter()
    css = """
        table, th, td {
            border: 1px solid black;
            border-collapse: collapse;
            vertical-align: top;
        }
        th, td {
            padding: 5px;
            text-align: left;
        }
        div.issue_text {
            max-width: 50em;
            padding: 5px;
            text-align: left;
            word-wrap: break-word;
        }
        """
    for label in database.label_db.all():
      css += """span.label-%s {
          background-color: #%s;
      }\n""" % (label.key, label.color)
    p.preamble(css)
    for category in c_groups.keys():
        p.write(p.B('Category: %s (%d issues)' % (category, len(c_groups[category]))))
        with p.table() as table:
            with table.row(heading=True) as row:
                row.cell('Issue')
                row.cell('Age')
                row.cell('Description')
            for issue in sorted(
                c_groups[category],
                reverse=True,
                key=lambda issue: latest_update_days_ago(issue)):
                with table.row() as row:
                    row.cell(issue_url(issue), rowspan=2, make_links=True)
                    with html_writer.HTMLWriter.TableCell(row,
                                               css_class='issue_text') as c:
                        c.write(p.B(issue['title']))
                        c.write(p.space(5))
                        # TODO(aiuto): If they are a Googler, put a G logo next to them.
                        # This is availble through github.corp.google.com API.
                        user =  database.created_by(issue)
                        c.write(p.Link(user.name, user.link))
                    with html_writer.HTMLWriter.TableCell(row, rowspan=2) as c:
                        c.write(p.B('%d days old'
                                    % latest_update_days_ago(issue)))
                        p.nl();
                        p.nl();
                        priority = get_priority(issue)
                        if priority:
                          l = database.label_db.get(priority)
                          c.write(p.B('Priority: %s' % label_html(l)))
                          p.nl();

                        p.nl();
                        c.write(p.B('Assignees:'))
                        assignees = issue['assignees']
                        if len(assignees) > 0:
                          for user_data in assignees:
                            user = database.User(user_data)
                            p.nl();
                            c.write(p.space(5))
                            c.write(p.Link(user.name, user.link))
                        else:
                          c.write(' [unassigned];')
                        p.nl();

                        c.write(p.B('Labels:'))
                        p.nl();
                        for label in issue['labels']:
                          name = label['name']
                          if not (name.startswith('P') and len(name) == 2):
                            c.write(p.space(5))
                            c.write(label_html(database.label_db.get(label)))
                            p.nl();

                        for cat in category_labels(issue['labels']):
                          proposed_team = CAT_2_TEAM.get(cat)
                          if proposed_team:
                            p.nl();
                            c.write(
                                """<button onclick="replaceLabel('%s', '%s', '%s')">"""
                                """Move to %s"""
                                """</button>""" % (
                                    issue['url'], cat, proposed_team,
                                    proposed_team))

                with table.row() as row:
                    row.cell(issue['body'], css_class='issue_text',
                             make_links=True)
    p.done()


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
            and not work_in_progress(issue) \
            and not has_label(issue, "release") \
            and not has_label(issue, "incompatible-change")

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
        printer=make_console_printer(
            show_age=True, show_number=False, show_title=True))


def garden(list_issues, list_pull_requests, stale_for_days):
    # We are only gardening open issues
    issues = database.get_issues(is_open)
    if list_issues:
        issues_to_garden(print_report, issues, stale_for_days)
    if list_pull_requests:
        pull_requests_to_garden(print_report, issues, stale_for_days)
