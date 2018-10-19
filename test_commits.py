from testfixtures.popen import MockPopen
from testfixtures import TempDirectory
import pytest
from testfixtures import OutputCapture
from unittest.mock import patch, DEFAULT
import sys
from contextlib import contextmanager
import subprocess
import logging
logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)

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

dummy_verify_expired = b"""gpg: Signature made Fri 25 May 15:29:58 2018 BST
gpg:                using RSA key 25C54F2464FFFF00A2B0031EB1EA0F133F6DAC7F
gpg: Good signature from "Foo <foo@bar.com>" [expired]
gpg: Note: This key has expired!"""

expired_key = """pub   rsa4096 2018-05-01 [SCEA] [expired: 2018-07-30]
      5092AC6B5AD6AEA069424FF0C50B04D24E7758D7
uid           [ expired] Foo <foo@bar.com>"""

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

def make_run(*args, **kwargs):
    if args == (['gpg', '--import'],):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=b'')
    elif args == (['gpg', '--list-keys', '25C54F2464FFFF00A2B0031EB1EA0F133F6DAC7F'],):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=expired_key)
    else:
        raise Exception(args)

@contextmanager
def checker():
    rollback = RollbackImporter()
    with TempDirectory() as d:
        popen = MockPopen()
        with patch('subprocess.run', new=make_run):
            with patch.multiple('subprocess', Popen=popen) as values:
                popen.set_command('git version', stdout=b'git version 2.14.3')
                popen.set_command('git rev-list foo --', stdout=commit_sha)
                sha_str = commit_sha.decode("utf-8")
                popen.set_command("git show %s" % sha_str, stdout=dummy_commit)
                from clincher import CommitChecker
                c = CommitChecker("foo", _TestArgs(manual_signing_path=d.path))
                with OutputCapture() as output:
                    yield {"output":output, "popen":popen, "checker":c, "sha":sha_str, "directory": d}
    rollback.uninstall()

def test_checker():
    with checker() as v:
        v["popen"].set_command('git cat-file --batch', stdout=dummy_rev)
        with pytest.raises(SystemExit):
            v["checker"].check()
        v["output"].compare('\n'.join([
            "%s Test commit False" % v["sha"],
            "Missing signature for %s by Foo" % v["sha"],
        ]))

def test_checker_with_file():
    with checker() as v:
        v["directory"].write("%s - Foo" % v["sha"], b"Blah")
        v["popen"].set_command('git cat-file --batch', stdout=dummy_rev)
        with pytest.raises(SystemExit):
            v["checker"].check()
        v["output"].compare('\n'.join([
            "%s Test commit False" % v["sha"],
            "Can't find signature file '%s/%s - Foo.signature' for %s" % (v["directory"].path, v["sha"], v["sha"])
        ]))

def test_signed_checker():
    with checker() as v:
        v["popen"].set_command('git cat-file --batch', stdout=signed_dummy_rev)
        v["popen"].set_command("git verify-commit %s" % v["sha"], stderr=dummy_verify)
        v["checker"].check()
        v["output"].compare('\n'.join([
            "All commits matching foo are signed"
        ]))

def test_expired_signed_checker():
    with checker() as v:
        v["popen"].set_command('git cat-file --batch', stdout=signed_dummy_rev)
        v["popen"].set_command("git verify-commit %s" % v["sha"], stderr=dummy_verify_expired, returncode=2)
        v["checker"].check()
        v["output"].compare('\n'.join([
            "All commits matching foo are signed"
        ]))