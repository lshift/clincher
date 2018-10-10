from testfixtures.popen import MockPopen
from testfixtures import TempDirectory
import pytest
from testfixtures import OutputCapture

class _TestArgs:
    key_path = "keys"
    manual_signing_path = "manual"
    git_path = "."
    name = "Foo"
    email = "foo@bar.com"

    def __init__(self, manual_signing_path=None):
        if manual_signing_path:
            self.manual_signing_path = manual_signing_path

commit_sha = b'4c6455b8efef9aa2ff5c0c844bb372bdb71eb4b1'

dummy_rev = b"""%s commit 209
tree 072e57c271f2a38a81291a7d162b7f99ac015fc9
author Foo <foo@bar.com> 1539166245 +0100
committer Foo <foo@bar.com> 1539166245 +0100

Test commit""" % commit_sha

dummy_commit = b"""commit %s
Author: Foo <foo@bar.com>
Date:   Wed Oct 10 11:10:45 2018 +0100

    Initial commit

diff --git a/Dockerfile b/Dockerfile
new file mode 100644
index 0000000..a47c0a9
--- /dev/null
+++ b/Dockerfile
@@ -0,0 +1,1 @@
+FROM python:3.6-slim""" % commit_sha

def test_checker(mocker):
    with TempDirectory() as d:
        run = mocker.patch('subprocess.run')
        popen = mocker.patch('subprocess.Popen', new_callable=MockPopen)
        popen.set_command('git version', stdout=b'git version 2.14.3', stderr=b'')
        popen.set_command('git rev-list foo --', stdout=commit_sha, stderr=b'')
        popen.set_command('git cat-file --batch', stdout=dummy_rev, stderr=b'')
        popen.set_command("git show %s" % commit_sha.decode("utf-8"), stdout=dummy_commit, stderr=b'')

        from check_commits import CommitChecker
        c = CommitChecker("foo", _TestArgs(manual_signing_path=d.path))
        with OutputCapture() as output:
            with pytest.raises(SystemExit):
                c.check()
            output.compare('\n'.join([
                "4c6455b8efef9aa2ff5c0c844bb372bdb71eb4b1 Test commit False",
                "Missing signature for 4c6455b8efef9aa2ff5c0c844bb372bdb71eb4b1 by Foo",
            ]))