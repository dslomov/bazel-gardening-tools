# Bazel Gardening Tools for GitHub Issues and PRs
## Overview

Tools for managing issues and pull requests on Bazel's GitHub repositories.

## Usage

### Set up GitHub secrets

First, create a `secrets.json` file in the root of the project repo with the following content:

```json
{
    "client_id": "",
    "client_secret": ""
}
```

Obtain the `client_id` and `client_secret` by creating an OAuth application at
https://github.com/settings/developers. The application name, homepage url and
callback url are irrelevant, so you can enter anything for them (e.g.
example.com for the urls).

The CLI is a python script. The primary purpose of the tool is to generate
reports of issues and pull requests. These reports are created from composable
queries, like `is_pull_request()`, `has_label()` and `is_work_in_progress()`.

```
$ ./issue-stats.py -h
usage: issue-stats.py [-h] [--verbose] {update,report,garden,html} ...

Gather Bazel's issues and pull requests data

positional arguments:
  {update,report,garden,html}
                        select a command
    update              update the datasets
    report              generate a full report
    garden              generate issues/pull requests that need gardening
                        attention
    html                generate HTML for issues/pull requests that need
                        attention

optional arguments:
  -h, --help            show this help message and exit
  --verbose             Be more verbose
```

### Fetch and update data

To obtain the issue datasets, first run a full fetch from GitHub:

```
$ ./issue-stats.py update --full
```

This will take a while. After you’ve completed a full fetch, omit `--full` from
future calls for incremental fetching:

```
$ ./issue-stats.py update
```

### Gardening

The `garden` command filters the list of issues and/or pull requests that
gardeners should pay attention to.

```
$ ./issue-stats.py garden -h
usage: issue-stats.py garden [-h] [-i] [-p] [-s STALE_FOR_DAYS]

optional arguments:
  -h, --help            show this help message and exit
  -i, --list_issues     list issues that need attention (true/false)
  -p, --list_pull_requests
                        list pull requests that need attention (true/false)
  -s STALE_FOR_DAYS, --stale_for_days STALE_FOR_DAYS
                        list issues/prs that have not been updated for more
                        than the specified number of days (number, default is
                        0)
```

The filters are written in terms of simple predicates in `reports.py`. Note that
some predicates are specific to the issue and PR lifecycles for the main Bazel
repository, defined in the [Bazel Maintainer’s
Guide](https://www.bazel.build/maintainers-guide.html#initial-routing).

```python
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
```

For example, to see the list of pull requests to be gardened for Bazel Front
End, run the following command (the command line output has been designed to be
friendly to unix tools like `grep`, `sort` and `sed`):

```
$ ./issue-stats.py garden -p \
  | grep "\(skydoc\|buildtools\|bazel-skylib\|starlark\|rules_jvm_external\|rules_foreign_cc\)" \
  | sort -n
3    | https://github.com/bazelbuild/bazel-skylib/pull/171 | fix broken CI: clean up linter failures and remo..
3    | https://github.com/bazelbuild/bazel-skylib/pull/175 | Add jin to codeowners                             
4    | https://github.com/bazelbuild/bazel-skylib/pull/172 | Update "Getting Started" instructions to 0.9.0 r..
5    | https://github.com/bazelbuild/bazel-skylib/pull/170 | Update selects documentation.                     
10   | https://github.com/bazelbuild/bazel-skylib/pull/162 | lib.bzl: replace the warning with an error        
37   | https://github.com/bazelbuild/rules_jvm_external/pull/168 | Allow in-source cache directory to store artifac..
54   | https://github.com/bazelbuild/buildtools/pull/642 | Support raw strings in the formatter              
73   | https://github.com/bazelbuild/skydoc/pull/103   | Support TreeArtifact output.                      
124  | https://github.com/bazelbuild/bazel-skylib/pull/41 | Add strings lib with strip_margin utility         
143  | https://github.com/bazelbuild/bazel-skylib/pull/115 | lint warning fix                                  
145  | https://github.com/bazelbuild/buildtools/pull/561 | Configure Renovate                                
146  | https://github.com/bazelbuild/skydoc/pull/162   | Configure Renovate                                
194  | https://github.com/bazelbuild/skydoc/pull/132   | Fix undefined name 'e' in rule_extractor.py       
222  | https://github.com/bazelbuild/buildtools/pull/313 | [buildozer] Add ability to print separators in o..
243  | https://github.com/bazelbuild/bazel-skylib/pull/61 | Add a repository.bzl helper                       
269  | https://github.com/bazelbuild/buildtools/pull/168 | buildozer: add command line flag to override bui..
559  | https://github.com/bazelbuild/buildtools/pull/179 | Add merge and copy_merge functionality  
```

These are **pull requests** without **team-* **labels and** assignees**, are
**not work in progress** (no `wip` label) and **passes Google CLA checks**. The
list is also sorted by **days since last update** in ascending order.

### Reports

The gardening list is just a special type of a `report`. To see the other report
types, use the `report` command:

```
$ ./issue-stats.py report -h
usage: issue-stats.py report [-h]
                             [-a | -r {more_than_one_team,issues_without_team,triaged_no_priority,unmigrated}]

optional arguments:
  -h, --help            show this help message and exit
  -a, --all             show all reports
  -r {more_than_one_team,issues_without_team,triaged_no_priority,unmigrated}, --report {more_than_one_team,issues_without_team,triaged_no_priority,unmigrated}
                        show selected report (multiple values possible)
```

Like the predicates for the `garden` command, these built-in reports are
specific to the main Bazel repository. However, one can easily create a custom
report by writing a query in `report.py`. For example, here is a query for stale
pull requests that have not been updated for more than 14 days:

```python
def stale_pull_requests(reporter, issues, days):
    def predicate(issue):
        return \
            is_open(issue) \
            and is_pull_request(issue) \
            and is_stale(issue, days) \
            and not work_in_progress(issue)

    reporter(
        issues,
        header="Stale pull requests for %s days" % days,
        predicate=predicate,
        printer=make_console_printer(show_title=True, show_age=True))

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
}
```

..which produces this report:

```
$ ./issue-stats.py report -r stale_pull_requests_14d \
  | grep "\(skydoc\|buildtools\|bazel-skylib\|starlark\|rules_jvm_external\|rules_foreign_cc\)" \
  | sort -n
21   | 278  | https://github.com/bazelbuild/rules_foreign_cc/pull/278 | Introduce clear_transitive_flags list attributes..
37   | 168  | https://github.com/bazelbuild/rules_jvm_external/pull/168 | Allow in-source cache directory to store artifac..
54   | 642  | https://github.com/bazelbuild/buildtools/pull/642 | Support raw strings in the formatter              
67   | 255  | https://github.com/bazelbuild/rules_foreign_cc/pull/255 | Fix #252 "ranlib issues with custom toolchains" ..
68   | 259  | https://github.com/bazelbuild/rules_foreign_cc/pull/259 | Bugfix: detect_root would like to fail when hand..
73   | 103  | https://github.com/bazelbuild/skydoc/pull/103   | Support TreeArtifact output.                      
124  | 41   | https://github.com/bazelbuild/bazel-skylib/pull/41 | Add strings lib with strip_margin utility         
125  | 33   | https://github.com/bazelbuild/bazel-skylib/pull/33 | Add a replacement for genrules in macros          
125  | 44   | https://github.com/bazelbuild/bazel-skylib/pull/44 | Add 'paths.relative_path' function                
143  | 115  | https://github.com/bazelbuild/bazel-skylib/pull/115 | lint warning fix                                  
145  | 561  | https://github.com/bazelbuild/buildtools/pull/561 | Configure Renovate                                
146  | 162  | https://github.com/bazelbuild/skydoc/pull/162   | Configure Renovate                                
191  | 50   | https://github.com/bazelbuild/buildtools/pull/50 | Windows: Use CRLF instead of LF when writing fil..
194  | 132  | https://github.com/bazelbuild/skydoc/pull/132   | Fix undefined name 'e' in rule_extractor.py       
222  | 313  | https://github.com/bazelbuild/buildtools/pull/313 | [buildozer] Add ability to print separators in o..
243  | 61   | https://github.com/bazelbuild/bazel-skylib/pull/61 | Add a repository.bzl helper                       
269  | 168  | https://github.com/bazelbuild/buildtools/pull/168 | buildozer: add command line flag to override bui..
294  | 90   | https://github.com/bazelbuild/skydoc/pull/90    | Refactor and update dependencies                  
362  | 35   | https://github.com/bazelbuild/buildtools/pull/35 | Make the width of the indent customizable.        
559  | 179  | https://github.com/bazelbuild/buildtools/pull/179 | Add merge and copy_merge functionality            
712  | 36   | https://github.com/bazelbuild/buildtools/pull/36 | Quote style                                       
712  | 66   | https://github.com/bazelbuild/buildtools/pull/66 | Cmd concat                                        
```

### Predicates

The current list of predicates are:

*   teams
*   has_team_label
*   latest_update_days_ago
*   is_stale
*   has_cla
*   work_in_progress
*   needs_more_data
*   has_priority / get_priority
*   get_any_of_labels
*   has_label
*   is_pull_request
*   is_open

See
[code](reports.py)(https://github.com/dslomov/bazel-gardening-tools/blob/19ba27a34b46bace0c98bcda84e79124e06cfdf6/reports.py#L63)</code>
for how these are defined.
