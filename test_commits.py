from testfixtures.popen import MockPopen
from testfixtures import TempDirectory
import pytest
from testfixtures import OutputCapture
from unittest.mock import patch, DEFAULT
import sys
from contextlib import contextmanager
import subprocess
import re
import os.path
import logging
logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)

class _TestArgs:
    key_path = "keys"
    manual_signing_path = "manual"
    git_path = "."
    name = "Foo"
    email = "foo@bar.com"
    rev_spec = None
    check_everything = False

    def __init__(self, **kwargs):
        for k in kwargs:
            setattr(self, k, kwargs[k])

commit_sha = b'4c6455b8efef9aa2ff5c0c844bb372bdb71eb4b1'
bad_signature_sha = b'66f5d00d1a31fdfb87b2080ffe72f9774c11e091'
wrong_signature_sha = b'd45b039f0703f471a69c8618d05422516ca4d249'

dummy_rev_pattern = b"""%s commit 209
tree 072e57c271f2a38a81291a7d162b7f99ac015fc9
author Foo <foo@bar.com> 1539166245 +0100
committer Foo <foo@bar.com> 1539166245 +0100

Test commit"""

dummy_rev = dummy_rev_pattern % commit_sha
bad_signature_rev = dummy_rev_pattern % bad_signature_sha
wrong_signature_rev = dummy_rev_pattern % wrong_signature_sha

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

first_parent = b"bed3cbfffc0851167b49b751db32212de2454f6c"
second_parent = b"5ad01b3ecce547eb3715188b1224beb04f411de6"

empty_merge_commit = b"""8e2f3256c3f1a3c305bffc6a0d8a1056f912ceb2 commit 808
tree 4f21e33ba1bffc725834bf9ddcb1f59ca15487dd
parent %s
parent %s
author Foo <foo@bar.com> 1539528686 +0100
gpgsig -----BEGIN PGP SIGNATURE-----
 wsBcBAABCAAQBQJbw1fuCRBK7hj4Ov3rIwAAdHIIACstihCi1/LRfuF1i7rtai9w
 aYvl+bkF2lILGL3ShOuMV9aNM/RUQnefEElzJ203E2xAbJUBr/J3U5t53m+9PbfH
 DRUfOLqflJLPX2W1zUKBWA60MuQtzbo4GMIHnAHU7nfPK83YHirM/WmsXmawIxf0
 iZ4bK8fQM/F24RBJb/+sElSInwDSSRlppzbZ3CiqXsnQf1UbJSHw9HLk7vAFK3xU
 MT/kffOxKTWMg7WS5yDm0C0SnTFg/2oIC2yMa/Qdim+vi9KYTTPSsb+sJX+rwHuv
 jwIa/TFkuWrT+ACtsJpaPzKsFULxBb4WiaOV2+T2ZiwAVp27nL/47vOzzkt471g=
 =BWDO
 -----END PGP SIGNATURE-----

Test merge commit""" % (first_parent, second_parent)

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

key_signature = b"5BBC2B94F704B8DE246E78C471951B6C037BC7A0"
older_key_signature = b"286781e812cd4c7f0a14a07c1a723425f97beb65"

dummy_verify = b"""gpg: Signature made Wed 10 Oct 16:13:01 2018 BST
gpg:                using RSA key %s
gpg: Good signature from "Foo <foo@bar.com>" [ultimate]""" % key_signature

dummy_verify_expired_template = b"""gpg: Signature made Fri 25 May 15:29:58 2018 BST
gpg:                using RSA key %s
gpg: Good signature from "Foo <foo@bar.com>" [expired]
gpg: Note: This key has expired!"""

dummy_verify_expired = dummy_verify_expired_template % key_signature
dummy_verify_expired_older = dummy_verify_expired_template % older_key_signature

expired_key = """pub   rsa4096 2018-05-01 [SCEA] [expired: 2018-07-30]
      %s
uid           [ expired] Foo <foo@bar.com>""" % key_signature

older_expired_key = """pub   rsa4096 2018-05-01 [SCEA] [expired: 2017-07-30]
      %s
uid           [ expired] Foo <foo@bar.com>""" % older_key_signature

good_signature = """gpg: Signature made Fri 19 Oct 21:20:15 2018 BST
gpg:                using RSA key %s
gpg: Good signature from "Foo <foo@bar.com>" [ultimate]""" % key_signature

no_key = b"""gpg: Signature made Fri May  4 14:27:18 2018 UTC
gpg:                using RSA key %s
gpg: Can't check signature: No public key""" % key_signature

not_detached_signature = "gpg: not a detached signature"

bad_signature_file = """gpg: no valid OpenPGP data found.
gpg: the signature could not be verified.
Please remember that the signature file (.sig or .asc)
should be the first file given on the command line."""

wrong_signature_file = """gpg: Signature made Sun 21 Oct 11:38:33 2018 BST
gpg:                using RSA key %s
gpg: BAD signature from "Foo <foo@bar.com>" [ultimate]""" % wrong_signature_sha.decode('utf-8')

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
    if args == (['gpg', '--import', os.path.join(os.path.dirname(__file__), 'keys/example_key.gpg')],):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=b'')
    elif args == (['gpg', '--list-keys', key_signature.decode('utf-8')],):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=expired_key)
    elif args == (['gpg', '--list-keys', older_key_signature.decode('utf-8')],):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=older_expired_key)
    elif args[0][:2] == ["gpg", "--verify"]:
        test_path = args[0][-1]
        if test_path.find(commit_sha.decode('utf-8')) != -1:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=good_signature)
        elif test_path.find(bad_signature_sha.decode('utf-8')) != -1:
            raise subprocess.CalledProcessError(returncode=2, cmd=args, output=bad_signature_file)
        elif test_path.find(wrong_signature_sha.decode('utf-8')) != -1:
            raise subprocess.CalledProcessError(returncode=2, cmd=args, output=wrong_signature_file)
        else:
            raise Exception(args[0])
    else:
        raise Exception(args)

@contextmanager
def checker(**kwargs):
    rollback = RollbackImporter()
    with TempDirectory() as d:
        popen = MockPopen()
        with patch('subprocess.run', new=make_run):
            with patch.multiple('subprocess', Popen=popen) as values:
                popen.set_command('git version', stdout=b'git version 2.14.3')
                popen.set_command('git rev-list HEAD...master --', stdout=commit_sha)
                sha_str = commit_sha.decode("utf-8")
                popen.set_command("git show %s" % sha_str, stdout=dummy_commit)
                from clincher import CommitChecker
                kwargs['manual_signing_path'] = d.path
                c = CommitChecker(_TestArgs(**kwargs))
                with OutputCapture() as output:
                    yield {"output":output, "popen":popen, "checker":c, "sha":sha_str, "directory": d}
    rollback.uninstall()

def test_checker():
    with checker() as v:
        v["popen"].set_command('git cat-file --batch', stdout=dummy_rev)
        with pytest.raises(SystemExit):
            v["checker"].check()
        v["output"].compare('\n'.join([
            "Problem at commit %s: Test commit (no signature)" % v["sha"],
            "Missing signature for %s by Foo" % v["sha"],
        ]))

def test_checker_with_file():
    with checker() as v:
        v["directory"].write("%s - Foo" % v["sha"], b"Blah")
        v["popen"].set_command('git cat-file --batch', stdout=dummy_rev)
        with pytest.raises(SystemExit):
            v["checker"].check()
        v["output"].compare('\n'.join([
            "Problem at commit %s: Test commit (no signature)" % v["sha"],
            "Can't find signature file '%s/%s - Foo.asc' for %s" % (v["directory"].path, v["sha"], v["sha"])
        ]))

def test_checker_with_signed_file():
    with checker() as v:
        v["directory"].write("%s - Foo" % v["sha"], b"Blah")
        v["directory"].write("%s - Foo.asc" % v["sha"], b"Blah signed")
        v["popen"].set_command('git cat-file --batch', stdout=dummy_rev)
        v["checker"].check()
        v["output"].compare('\n'.join([
            "All commits between HEAD...master are signed"
        ]))

def test_checker_with_dodgy_signed_file():
    with checker() as v:
        v["popen"].set_command('git rev-list HEAD...master --', stdout=bad_signature_sha)
        v["popen"].set_command('git cat-file --batch', stdout=bad_signature_rev)
        bad_sig_sha_str = bad_signature_sha.decode('utf-8')
        v["popen"].set_command("git show %s" % bad_sig_sha_str, stdout=dummy_commit)
        v["directory"].write("%s - Foo" % bad_sig_sha_str, b"Blah")
        v["directory"].write("%s - Foo.asc" % bad_sig_sha_str, b"Blah signed")
        with pytest.raises(SystemExit):
            v["checker"].check()
        compare_str = '\n'.join([
            "Problem at commit %s: Test commit \(no signature\)" % bad_sig_sha_str,
            "Bad signature data in .*?%s - Foo. May not be valid GPG file?" % bad_sig_sha_str
        ])
        assert re.match(compare_str, v["output"].captured)

def test_checker_with_wrongly_signed_file():
    with checker() as v:
        v["popen"].set_command('git rev-list HEAD...master --', stdout=wrong_signature_sha)
        v["popen"].set_command('git cat-file --batch', stdout=wrong_signature_rev)
        wrong_sig_sha_str = wrong_signature_sha.decode('utf-8')
        v["popen"].set_command("git show %s" % wrong_sig_sha_str, stdout=dummy_commit)
        v["directory"].write("%s - Foo" % wrong_sig_sha_str, b"Blah")
        v["directory"].write("%s - Foo.asc" % wrong_sig_sha_str, b"Blah signed")
        with pytest.raises(SystemExit):
            v["checker"].check()
        v["output"].compare('\n'.join([
            "Problem at commit %s: Test commit (no signature)" % wrong_sig_sha_str,
            "Bad signature for %s. Did you sign the right file?" % wrong_sig_sha_str
        ]))

def test_signed_checker():
    with checker() as v:
        v["popen"].set_command('git cat-file --batch', stdout=signed_dummy_rev)
        v["popen"].set_command("git verify-commit %s" % v["sha"], stderr=dummy_verify)
        v["checker"].check()
        v["output"].compare('\n'.join([
            "All commits between HEAD...master are signed"
        ]))

def test_expired_signed_checker():
    with checker() as v:
        v["popen"].set_command('git cat-file --batch', stdout=signed_dummy_rev)
        v["popen"].set_command("git verify-commit %s" % v["sha"], stderr=dummy_verify_expired, returncode=2)
        v["checker"].check()
        v["output"].compare('\n'.join([
            "All commits between HEAD...master are signed"
        ]))

def test_expired_too_old_signed_checker():
    with checker() as v:
        v["popen"].set_command('git cat-file --batch', stdout=signed_dummy_rev)
        v["popen"].set_command("git verify-commit %s" % v["sha"], stderr=dummy_verify_expired_older, returncode=2)
        with pytest.raises(SystemExit):
            v["checker"].check()
        v["output"].compare('\n'.join([
            "Problem at commit %s: Test commit" % v["sha"],
            "Key %s expired on 2017-07-30 23:59:00+01:00 and the commit was on 2018-05-25 15:29:58+11:00" % older_key_signature.decode('utf-8')
        ]))

def test_no_key_signed_checker():
    with checker() as v:
        v["popen"].set_command('git cat-file --batch', stdout=signed_dummy_rev)
        v["popen"].set_command("git verify-commit %s" % v["sha"], stderr=no_key, returncode=2)
        with pytest.raises(SystemExit):
            v["checker"].check()
        v["output"].compare('\n'.join([
            "Problem at commit %s: Test commit" % v["sha"],
            "No key available for Foo <foo@bar.com>. We were looking for key with id %s" % key_signature.decode('utf-8')
        ]))


def test_checker_with_everything():
    with checker(check_everything=True) as v:
        v["popen"].set_command('git cat-file --batch', stdout=signed_dummy_rev)
        v["popen"].set_command('git cat-file --batch-check', stdout=signed_dummy_rev)
        v["popen"].set_command('git rev-list %s --' % v['sha'], stdout=commit_sha)
        v["popen"].set_command("git verify-commit %s" % v["sha"], stderr=dummy_verify)
        v["checker"].check()
        v["output"].compare('\n'.join([
            "All commits in repo are signed"
        ]))

def test_empty_merge_commit():
    with checker() as v:
        v["popen"].set_command('git cat-file --batch', stdout=empty_merge_commit)
        v["popen"].set_command('git show %s --format=' % v["sha"], stdout=b"")
        v["checker"].check()
        v["output"].compare('\n'.join([
            "All commits between HEAD...master are signed"
        ]))

def test_merge_commit():
    with checker() as v:
        v["popen"].set_command('git cat-file --batch', stdout=empty_merge_commit)
        expected_differences = b"differences"
        v["popen"].set_command('git show %s --format=' % v["sha"], stdout=expected_differences)
        v["popen"].set_command('git reset --hard %s' % first_parent.decode("utf-8"), stdout=b"HEAD is now at %s test commit" % first_parent[:7])
        v["popen"].set_command('git -c commit.gpgsign=false merge %s --no-edit' % second_parent.decode('utf-8'), stdout=b'')
        v["popen"].set_command('git show HEAD --format=', stdout=expected_differences)
        v["checker"].check()
        v["output"].compare('\n'.join([
            "All commits between HEAD...master are signed"
        ]))

def test_conflicting_merge_commit():
    with checker() as v:
        v["popen"].set_command('git cat-file --batch', stdout=empty_merge_commit)
        expected_differences = b"differences"
        v["popen"].set_command('git show %s --format=' % v["sha"], stdout=expected_differences)
        v["popen"].set_command('git reset --hard %s' % first_parent.decode("utf-8"), stdout=b"HEAD is now at %s test commit" % first_parent[:7])
        v["popen"].set_command('git -c commit.gpgsign=false merge %s --no-edit' % second_parent.decode('utf-8'), stdout=b"""CONFLICT (content): Merge conflict in src/common.rs
Automatic merge failed; fix conflicts and then commit the result.""", returncode=1)
        with pytest.raises(SystemExit):
            v["checker"].check()
        v["output"].compare('\n'.join([
            "Problem at commit %s: Test merge commit (no signature)" % v["sha"],
            "Unsigned conflicting merge found, which we can't check"
        ]))

def test_different_merge_commit():
    with checker() as v:
        v["popen"].set_command('git cat-file --batch', stdout=empty_merge_commit)
        v["popen"].set_command('git show %s --format=' % v["sha"], stdout=b"differences")
        v["popen"].set_command('git reset --hard %s' % first_parent.decode("utf-8"), stdout=b"HEAD is now at %s test commit" % first_parent[:7])
        v["popen"].set_command('git -c commit.gpgsign=false merge %s --no-edit' % second_parent.decode('utf-8'), stdout=b'')
        v["popen"].set_command('git show HEAD --format=', stdout=b"other differences")
        with pytest.raises(SystemExit):
            v["checker"].check()
        v["output"].compare('\n'.join([
            "Problem at commit %s: Test merge commit (no signature)" % v["sha"],
            "Unsigned merge whose diff varies from what would be expected. Bad third-party merge?"
        ]))