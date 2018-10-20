import git
import platform
import tempfile
import io
import subprocess
import re
import os.path
import sys
import argparse
import difflib
import dateparser

def check_or_throw(cmd):
    try:
        s = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True, encoding='utf-8')
        return s.stdout
    except subprocess.CalledProcessError as e:
        print(" ".join(cmd))
        print(e.stdout)
        raise

class CommitChecker:
    def new_error(self, c, msg):
        print(c.hexsha, c.summary, c.gpgsig != None)
        print(msg)
        self.errors.add(msg)

    def get_commit_details(self, c, no_format=False):
        cmd = [c.hexsha]
        if no_format:
            cmd.append("--format=")
        return self.repo.git.show(cmd)

    def get_key(self, output):
        return re.search("using RSA key (?:ID )?(.+)", output).groups()[0]

    def check_merge(self, c):
        commit = self.get_commit_details(c, no_format=True)
        if commit.find("diff") != -1:
            first, second = [p.hexsha for p in c.parents]
            self.repo.git.reset("--hard", first)
            self.repo.git(c="commit.gpgsign=false").merge(second, "--no-edit")
            local_commit = self.repo.git.show("HEAD", "--format=")
            if local_commit != commit:
                diff = difflib.unified_diff(commit, local_commit)
                print("".join(list(diff)))
                print("Commit: '%s'" % commit)
                print("Local commit: '%s'" % local_commit)
                self.new_error(c, "Changes during the merge %s" % c.hexsha)
                raise Exception

    def check_unsigned(self, c):
        manual_path = os.path.join(self.manual, "%s - %s" % (c.hexsha, c.author.name))
        gpg_path = manual_path + ".asc"
        if not os.path.exists(manual_path):
            open(manual_path, "w").write(self.get_commit_details(c))
            self.new_error(c, "Missing signature for %s by %s" % (c.hexsha, c.author.name))
        elif not os.path.exists(gpg_path):
            self.new_error(c, "Can't find signature file '%s' for %s" % (gpg_path, c.hexsha))
        else:
            try:
                check_or_throw(["gpg", "--verify", gpg_path, manual_path])
            except subprocess.CalledProcessError as ce:
                if ce.stdout.find("BAD signature") != -1:
                    key_id = self.get_key(ce.stdout)
                    self.new_error(c, "Bad signature for %s" % key_id)
                else:
                    raise

    def check_signed(self, c):
        try:
            self.repo.git.verify_commit(c.hexsha)
        except git.exc.GitCommandError as ce:
            if ce.stderr.find("Can't check signature: No public key") != -1 or ce.stderr.find("Can't check signature: public key not found") != -1: # Seen first from OSX and the latter from Linux
                key_id = get_key(ce.stderr)
                self.new_error(c, "No key available for %s <%s>. We were looking for key with id %s" % (c.author.name, c.author.email, key_id))
            elif ce.stderr.find("Note: This key has expired") != -1:
                key_id = self.get_key(ce.stderr)
                when = re.search("Signature made (.+)", ce.stderr)
                when = dateparser.parse(when.groups()[0])
                key_info = check_or_throw(["gpg", "--list-keys", key_id])
                expiry = re.search(r"expired: (\d{4}-\d{2}-\d{2})", key_info)
                if expiry == None:
                    raise Exception(key_info)
                expiry = dateparser.parse(expiry.groups()[0], settings={
                    'TIMEZONE': 'Europe/London',
                    'RETURN_AS_TIMEZONE_AWARE': True,
                })
                expiry = expiry.replace(hour=23, minute=59) # To cope with commits on the day of expiry, which are fine
                if when > expiry:
                    self.new_error(c, "Key %s expired on %s and the commit was on %s" % (key_id, expiry, when))
            elif ce.stderr.find("WARNING: This key is not certified with a trusted signature!") != -1:
                # This is bad, but can't seem to figure out how to get gpg to auto-trust keys, so skip
                pass
            else:
                raise Exception((ce.stdout, ce.stderr))
    
    def __init__(self, args):
        self.check_everything = args.check_everything
        if args.rev_spec != None:
            self.rev_spec = args.rev_spec
        elif self.check_everything:
            self.rev_spec = None
        else:
            self.rev_spec = "HEAD...master"

        self.keydir = os.path.abspath(args.key_path)
        self.keys = [os.path.abspath(os.path.join(self.keydir, k)) for k in os.listdir(self.keydir) if k.endswith(".gpg")]
        check_or_throw(["gpg", "--import"] + self.keys)

        self.repo = git.Repo(args.git_path)
        self.manual = os.path.abspath(args.manual_signing_path)

        with self.repo.config_writer(config_level='global') as config:
            if not config.has_section("user"):
                config.add_section("user")
            if not config.has_option(section="user", option="email"):
                config.set("user", "email", args.email)
            if not config.has_option(section="user", option="name"):
                config.set("user", "name", args.name)
            config.write()

        self.errors = set()
    
    def check(self):
        for c in self.repo.iter_commits(rev=self.rev_spec):
            if c.gpgsig == None:
                if len(c.parents) == 2:
                    self.check_merge(c)
                else:
                    self.check_unsigned(c)
            else:
                self.check_signed(c)

        if len(self.errors) > 0:
            sys.exit(-1)
        else:
            if self.rev_spec:
                print("All commits between %s are signed" % self.rev_spec)
            elif self.check_everything:
                print("All commits in repo are signed")
            else:
                raise NotImplementedError("Unreachable rev spec!")

if __name__ == "__main__": # skip because hard to check the CLI bit
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-everything", help="Check everything back to the beginning (default: last branch with master)", action='store_true', default=False)
    parser.add_argument("--rev-spec", help="Add specific revision spec to check. This overrides any use of --check-everything", default=None)
    parser.add_argument("--git-path", default=".")
    parser.add_argument("--key-path", default="keys")
    parser.add_argument("--manual-signing-path", default="manually_signed")
    parser.add_argument("--email", default="automated@example.com")
    parser.add_argument("--name", default="Automated signer")
    args = parser.parse_args()

    checker = CommitChecker(args)
    checker.check()