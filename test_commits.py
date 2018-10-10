from testfixtures.popen import MockPopen
from testfixtures import TempDirectory
import pytest
from testfixtures import OutputCapture
from unittest.mock import patch, DEFAULT
import sys

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

signed_dummy_rev = b"""%s commit 759
tree fc7aee104fb49559b7cecd29317ad6055da71e4a
parent caf701edfdc10239a689db5635ec130d03a13f6c
author Foo <foo@bar.com> 1539166245 +0100
committer Foo <foo@bar.com> 1539166245 +0100
gpgsig -----BEGIN PGP SIGNATURE-----

 iQEzBAABCAAdFiEEdLV/PuDAFbtjk09EJnscrwkL+mcFAlu+Fv0ACgkQJnscrwkL
 +mceHQgAsFNJ+aGWJSuBqimyvA3fQw6LkShzNsb3mirLdawv+BOCxw2tEK/NFoGo
 JL3E11fRajxhtP2rsQXLEqvvDYFltoesqAsdJ85bXo09zZZ2qXR1CPzWfg3PjKw2
 lt4xHxh5R7/jHI3VRy3CrKiOHObrtuhmzu+0tMJoHQmqgRDHaqVBdwh/5MCkHb4X
 nlHh1s21dtTuVjYKEvMR5pdh5SLxBbS4b6+hxHzosfNp01ZZ/Zr4shYeEwbh/aId
 wFRFssDVqyHe6QH3mCTkn7F9Ji1tU5a9HLByWh6qv5xt1Wg7Q04vBIeQ/1apHMWH
 CDs6/WytisXo4dxdNCaxvJLk2daIUw==
 =VQYA
 -----END PGP SIGNATURE-----

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

dummy_verify = b"""gpg: Signature made Wed 10 Oct 16:13:01 2018 BST
gpg:                using RSA key 74B57F3EE0C015BB63934F44267B1CAF090BFA67
gpg: Good signature from "Foo <foo@bar.com>" [ultimate]"""

class RollbackImporter:
    def __init__(self):
        sys.meta_path.insert(0, self)
        self.previousModules = sys.modules.copy()
        self.newModules = {}

    def find_spec(self, fullname, path, target=None):
        self.newModules[fullname] = 1
        return None

    def uninstall(self):
        for modname in self.newModules.keys():
            if not modname in self.previousModules:
                if modname in sys.modules:
                    del(sys.modules[modname])

def test_checker():
    rollback = RollbackImporter()
    with TempDirectory() as d:
        popen = MockPopen()
        with patch.multiple('subprocess', run=DEFAULT, Popen=popen) as values:
            popen.set_command('git version', stdout=b'git version 2.14.3', stderr=b'')
            popen.set_command('git rev-list foo --', stdout=commit_sha, stderr=b'')
            popen.set_command('git cat-file --batch', stdout=dummy_rev, stderr=b'')
            sha_str = commit_sha.decode("utf-8")
            popen.set_command("git show %s" % sha_str, stdout=dummy_commit, stderr=b'')

            from check_commits import CommitChecker
            c = CommitChecker("foo", _TestArgs(manual_signing_path=d.path))
            with OutputCapture() as output:
                with pytest.raises(SystemExit):
                    c.check()
                output.compare('\n'.join([
                    "%s Test commit False" % sha_str,
                    "Missing signature for %s by Foo" % sha_str,
                ]))
    rollback.uninstall()

def test_signed_checker():
    rollback = RollbackImporter()
    with TempDirectory() as d:
        popen = MockPopen()
        with patch.multiple('subprocess', run=DEFAULT, Popen=popen) as values:
            popen.set_command('git version', stdout=b'git version 2.14.3', stderr=b'')
            popen.set_command('git rev-list foo --', stdout=commit_sha, stderr=b'')
            popen.set_command('git cat-file --batch', stdout=signed_dummy_rev, stderr=b'')
            sha_str = commit_sha.decode("utf-8")
            popen.set_command("git show %s" % sha_str, stdout=dummy_commit, stderr=b'')
            popen.set_command("git verify-commit %s" % sha_str, stdout=dummy_verify, stderr=b'')

            from check_commits import CommitChecker
            c = CommitChecker("foo", _TestArgs(manual_signing_path=d.path))
            with OutputCapture() as output:
                c.check()
                output.compare('\n'.join([
                    "All commits matching foo are signed"
                ]))
    rollback.uninstall()