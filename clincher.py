"""Clincher is a tool for checking that all the commits in a git repo are signed"""

__version__ = '0.1'

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
import shutil
import tempfile

def check_or_throw(cmd, quiet=False):
    try:
        s = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True, encoding='utf-8')
        return s.stdout
    except subprocess.CalledProcessError as e:
        if not quiet:
            print(" ".join(cmd))
            print(e.stdout)
        raise

class CommitChecker:
    def new_error(self, c, msg):
        if c != None:
            print("Problem at commit %s: %s%s" %(c.hexsha, c.summary, " (no signature)" if c.gpgsig == None else ""))
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
            try:
                self.repo.git(c="commit.gpgsign=false").merge(second, "--no-edit")
            except git.GitCommandError as e:
                if e.stdout.find("Automatic merge failed") != -1:
                    self.new_error(c, "Unsigned conflicting merge found, which we can't check")
                else:
                    self.new_error(c, "Error while trying to check merge: %s" % e.stdout)
                return
            local_commit = self.repo.git.show("HEAD", "--format=")
            if local_commit != commit:
                diff = difflib.unified_diff(commit, local_commit)
                self.new_error(c, "Unsigned merge whose diff varies from what would be expected. Bad third-party merge?")

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
                check_or_throw(["gpg", "--verify", gpg_path, manual_path], quiet=True)
            except subprocess.CalledProcessError as ce:
                if ce.stdout.find("BAD signature") != -1:
                    key_id = self.get_key(ce.stdout)
                    self.new_error(c, "Bad signature for %s. Did you sign the right file?" % key_id)
                elif ce.stdout.find("the signature could not be verified"):
                    self.new_error(c, "Bad signature data in %s. May not be valid GPG file?" % manual_path)
                else:
                    raise

    def check_signed(self, c):
        try:
            self.repo.git.verify_commit(c.hexsha)
        except git.exc.GitCommandError as ce:
            if ce.stderr.find("Can't check signature: No public key") != -1 or ce.stderr.find("Can't check signature: public key not found") != -1: # Seen first from OSX and the latter from Linux
                key_id = self.get_key(ce.stderr)
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
                # FIXME: Historical issue that I can't seem to reproduce any more...
                pass
            else:
                raise Exception((ce.stdout, ce.stderr))

    def exit_error(self, message):
        print(message)
        sys.exit(-1)
    
    def __init__(self, args):
        self.temp_git_path = tempfile.TemporaryDirectory()
        if args.rev_spec != None:
            self.rev_spec = args.rev_spec
        else:
            self.rev_spec = None

        self.keydir = os.path.abspath(args.key_path)
        if not os.path.exists(self.keydir):
            self.exit_error("Can't find key path %s" % self.keydir)
        self.keys = [os.path.abspath(os.path.join(self.keydir, k)) for k in os.listdir(self.keydir) if k.endswith(".gpg")]
        if len(self.keys) > 0:
            check_or_throw(["gpg", "--import"] + self.keys)

        temp_git_root = self.temp_git_path.name + "/.git"
        local_git_root = args.git_path + "/.git"
        if not os.path.exists(local_git_root):
            self.exit_error("Can't find .git folder under %s" % os.path.abspath(args.git_path))
        shutil.copytree(local_git_root, temp_git_root)
        self.repo = git.Repo(temp_git_root)
        self.manual = os.path.abspath(args.manual_signing_path)
        if not os.path.exists(self.manual):
            self.exit_error("Can't find manual signing path %s" % self.manual)

        with self.repo.config_writer(config_level='global') as config:
            if not config.has_option(section="user", option="email"):
                self.exit_error("No user.email configured in git. Please fix this.")
            if not config.has_option(section="user", option="name"):
                self.exit_error("No user.name configured in git. Please fix this.")
            config.write()

        self.errors = set()
    
    def check(self):
        try:
            for c in self.repo.iter_commits(rev=self.rev_spec):
                if c.gpgsig == None:
                    if len(c.parents) == 2:
                        self.check_merge(c)
                    else:
                        self.check_unsigned(c)
                else:
                    self.check_signed(c)
        except git.GitCommandError as e:
            if e.stderr.find("fatal: bad revision") != -1:
                self.new_error(None, "Bad rev spec: '%s'" % self.rev_spec)
            else:
                raise

        if len(self.errors) > 0:
            sys.exit(-1)
        else:
            if self.rev_spec:
                print("All commits between %s are signed" % self.rev_spec)
            else:
                print("All commits are signed")

    def __del__(self):
        self.temp_git_path.cleanup()

def main(): # skip because hard to check the CLI bit
    parser = argparse.ArgumentParser()
    parser.add_argument("--rev-spec", help="Add specific revision spec to check", default=None)
    parser.add_argument("--git-path", default=".", help="Path to git repo (default: this directory)")
    parser.add_argument("--key-path", default="keys", help="Path to GPG keys (default: keys)")
    parser.add_argument("--manual-signing-path", default="manually_signed", help="Path to manually signed files (default: manually_signed)")
    args = parser.parse_args()

    checker = CommitChecker(args)
    checker.check()

if __name__ == "__main__": # skip because hard to check the CLI bit
    main()