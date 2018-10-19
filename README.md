Clincher
========
[![Build Status](https://travis-ci.org/lshift/clincher.svg?branch=master)](https://travis-ci.org/lshift/clincher)

`clincher` is a tool for checking that all the commits in a git repo are signed, or if they're not that someone has signed something afterwards to backfill that.

By default, `python clincher.py` will check only the commits between current HEAD and master and assume the git repo is two directories above the current folder

* `--check-everything` will check all the commits in the git log
* `--rev-spec` allows for checking everything in a git rev spec (as per https://git-scm.com/docs/gitrevisions#_specifying_ranges). This is needed for Jenkins support as it doesn't have a "master" branch, but "remotes/upstream/master" does exist
* `--git-path` allows for specifying the root directory

If a commit isn't signed, a file will be generated in the "manually_signed" folder corresponding to that commit.

"keys" contains a list of the GPG keys for all trusted users, which will be automatically imported by the tool.