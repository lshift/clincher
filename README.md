Clincher
========
[![Build Status](https://travis-ci.org/lshift/clincher.svg?branch=master)](https://travis-ci.org/lshift/clincher)
[![Coverage Status](https://coveralls.io/repos/github/lshift/clincher/badge.svg)](https://coveralls.io/github/lshift/clincher)
![PyPI](https://img.shields.io/pypi/v/clincher.svg)
![PyPI - License](https://img.shields.io/pypi/l/clincher.svg)

`clincher` is a tool for checking that all the commits in a git repo are signed, or if they're not that someone has signed something afterwards to backfill that.

It implicitly trusts all the keys that are in the git repository, and dealing with keys that shouldn't be there is currently out of scope.

Installation
------------
1. [Install Python 3.X](https://www.python.org/downloads/)
2. `pip install clincher`

Options
-------
* `--rev-spec`: to check only the revisions in a git rev spec (as per https://git-scm.com/docs/gitrevisions#_specifying_ranges). Default is to check everything.
* `--git-path`: specify the root directory of the git repo (defaults to the current directory)
* `--key-path`: specify the keys path (default is "keys")
* `--manual-signing-path`: specify the manually signed commits path (default is "manually_signed")

Trusted keys
------------
The `key-path` folder contains a list of the GPG keys for all trusted users, which will be automatically imported by the tool. To export a key in the format we expect run `gpg --export --armor <key id>` (taking the key id from `gpg --list-keys`) and write it to a file
in `key-path` ending with ".gpg". We suggest using the users name and today's date to allow for identification and coping with expired keys.

Please note that even if a key is expired, if it's been used to sign historical commits prior to it's expiry it should be kept, as otherwise you have a commit we don't know how to verify.

Unsigned commits
----------------
If a commit isn't signed, a file will be generated in the `manual-signing-path` folder corresponding to that commit. This is a representation of the commit that can be signed as a way to backfill the missing signing without editing the git history, and will be treated the same as the commit itself. It is named `<git hash> - <author>`.

To sign the commit, use the following

`gpg --sign --armor --detach-sign <commit file>`

This file should be named `<git hash> - <author>.asc`

Uploading new versions to PyPi
------------------------------
We use [Flit](https://flit.readthedocs.io/en/latest/) for uploading so the following works

`FLIT_USERNAME="<pypi username>" FLIT_PASSWORD="<pypi password>" flit publish`