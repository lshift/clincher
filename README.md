Clincher
========
[![Build Status](https://travis-ci.org/lshift/clincher.svg?branch=master)](https://travis-ci.org/lshift/clincher)

`clincher` is a tool for checking that all the commits in a git repo are signed, or if they're not that someone has signed something afterwards to backfill that.

By default, `python clincher.py` will check only the commits between current HEAD and master and assume the git repo is two directories above the current folder

* `--check-everything` will check all the commits in the git log
* `--rev-spec` allows for checking everything in a git rev spec (as per https://git-scm.com/docs/gitrevisions#_specifying_ranges). This is needed for Jenkins support as it doesn't have a "master" branch, but "remotes/upstream/master" does exist
* `--git-path` allows for specifying the root directory

If a commit isn't signed, a file will be generated in the "manually_signed" folder corresponding to that commit

To sign the commit, use the following
`gpg --sign --armor --detach-sign manually_signed/<commit file>`

"keys" contains a list of the GPG keys for all trusted users, which will be automatically imported by the tool. To export a key in the format we expect
`gpg --export --armor 5BBC2B94F704B8DE246E78C471951B6C037BC7A0` (replacing the "5BB..." block with your key id from `gpg --list-keys`) and write it to a file
in "keys" ending with ".gpg". We suggest using the users name and today's date to allow for identification and coping with expired keys. Please note that
even if a key is expired, if it's been used to sign historical commits prior to it's expiry it should be kept!