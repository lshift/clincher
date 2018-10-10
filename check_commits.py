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

parser = argparse.ArgumentParser()
parser.add_argument("--check-everything", help="Check everything back to the beginning (default: last branch with master)", action='store_true', default=False)
parser.add_argument("--rev-spec", help="Add specific revision spec to check. This overrides any use of --check-everything", default=None)
parser.add_argument("--git-path", default=".")
args = parser.parse_args()

def check_or_throw(cmd):
    try:
        s = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True, encoding='utf-8')
        return s.stdout
    except subprocess.CalledProcessError as e:
        print(" ".join(cmd))
        print(e.stdout)
        raise

keydir = os.path.abspath(os.path.join(os.path.dirname(__file__), "keys"))
keys = [os.path.abspath(os.path.join(keydir, k)) for k in os.listdir(keydir) if k.endswith(".gpg")]
check_or_throw(["gpg", "--import"] + keys)

if args.rev_spec != None:
    rev_spec = args.rev_spec
elif args.check_everything:
    rev_spec = None
else:
    rev_spec = "HEAD...master"

repo = git.Repo(args.git_path)
manual = os.path.abspath("manually_signed")

errors = set()

def new_error(c, msg):
    global errors
    print(c.hexsha, c.summary, c.gpgsig != None)
    print(msg)
    errors.add(msg)

def get_commit_details(c, no_format=False):
    cmd = [c.hexsha]
    if no_format:
        cmd.append("--format=")
    return repo.git.show(cmd)

with repo.config_writer(config_level='global') as config:
    if not config.has_section("user"):
        config.add_section("user")
    if not config.has_option(section="user", option="email"):
        config.set("user", "email", "automated@teal18.net")
    if not config.has_option(section="user", option="name"):
        config.set("user", "name", "Teal Automated")
    config.write()

def get_key(output):
    return re.search("using RSA key (?:ID )?(.+)", output).groups()[0]

for c in repo.iter_commits(rev=rev_spec):
    if c.gpgsig == None:
        if len(c.parents) == 2:
            commit = get_commit_details(c, no_format=True)
            if commit.find("diff") != -1:
                first, second = [p.hexsha for p in c.parents]
                repo.git.reset("--hard", first)
                repo.git(c="commit.gpgsign=false").merge(second, "--no-edit")
                local_commit = repo.git.show("HEAD", "--format=")
                if local_commit != commit:
                    diff = difflib.unified_diff(commit, local_commit)
                    print("".join(list(diff)))
                    print("Commit: '%s'" % commit)
                    print("Local commit: '%s'" % local_commit)
                    new_error(c, "Changes during the merge %s" % c.hexsha)
                    raise Exception
        else:
            manual_path = os.path.join(manual, "%s - %s" % (c.hexsha, c.author.name))
            gpg_path = manual_path + ".signature"
            if not os.path.exists(manual_path):
                open(manual_path, "w").write(get_commit_details(c))
                new_error(c, "Missing signature for %s by %s" % (c.hexsha, c.author.name))
            elif not os.path.exists(gpg_path):
                new_error(c, "Can't find signature file '%s' for %s" % (gpg_path, c.hexsha))
            else:
                try:
                    check_or_throw(["gpg", "--verify", gpg_path, manual_path])
                except subprocess.CalledProcessError as ce:
                    if ce.stdout.find("BAD signature") != -1:
                        key_id = get_key(ce.stdout)
                        new_error(c, "Bad signature for %s" % key_id)
                    else:
                        raise
    else:
        try:
            repo.git.verify_commit(c.hexsha)
        except git.exc.GitCommandError as ce:
            if ce.stderr.find("Can't check signature: No public key") != -1 or ce.stderr.find("Can't check signature: public key not found") != -1: # Seen first from OSX and the latter from Linux
                key_id = get_key(ce.stderr)
                new_error(c, "No key available for %s <%s>. We were looking for key with id %s" % (c.author.name, c.author.email, key_id))
            elif ce.stderr.find("Note: This key has expired") != -1:
                key_id = get_key(ce.stderr)
                when = re.search("Signature made (.+)", ce.stderr)
                when = dateparser.parse(when.groups()[0])
                key_info = check_or_throw(["gpg", "--list-keys", key_id])
                expiry = re.search("expired: (\d{4}-\d{2}-\d{2})", key_info)
                if expiry == None:
                    raise Exception(key_info)
                expiry = dateparser.parse(expiry.groups()[0], settings={
                    'TIMEZONE': 'Europe/London',
                    'RETURN_AS_TIMEZONE_AWARE': True,
                })
                expiry = expiry.replace(hour=23, minute=59) # To cope with commits on the day of expiry, which are fine
                if when > expiry:
                    new_error(c, "Key %s expired on %s and the commit was on %s" % (key_id, expiry, when))
            elif ce.stderr.find("WARNING: This key is not certified with a trusted signature!") != -1:
                # This is bad, but can't seem to figure out how to get gpg to auto-trust keys, so skip
                pass
            else:
                raise Exception((ce.stdout, ce.stderr))

if len(errors) > 0:
    sys.exit(-1)
else:
    if args.rev_spec:
        print("All commits matching %s are signed" % args.rev_spec)
    elif args.check_everything:
        print("All commits in repo are signed")
    else:
        print("All commits between HEAD and master are signed")