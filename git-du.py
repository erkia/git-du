#!/usr/bin/env python3

from __future__ import print_function

import datetime
import math
import re
import subprocess
import sys

packed_objects = {}
seen_objects = {}


### Logging functions #########################################################

is_nln = False
nln_len = 0

def log_write (logstr):
    global is_nln, nln_len
    if (is_nln): sys.stderr.write ("\r" + (" " * nln_len) + "\r")
    print (logstr, file = sys.stderr)
    sys.stderr.flush()
    is_nln = False

def log_write_nln (logstr):
    global is_nln, nln_len
    sys.stderr.write ("\r" + logstr)
    sys.stderr.flush()
    nln_len = len (logstr)
    is_nln = True

###############################################################################


### Git functions #############################################################

def get_git_dir (working_dir):

    git_dir = "";

    hnd = subprocess.Popen (["git", "-C", working_dir, "rev-parse", "--show-toplevel"], stdout = subprocess.PIPE, stderr = subprocess.PIPE, close_fds = True)
    streams = hnd.communicate ();

    if (hnd.returncode == 0):
        for line in streams[0].splitlines ():
            git_dir = line.decode() + "/.git"
            break

    return git_dir


def get_pack_files (git_dir):

    packs = []

    hnd = subprocess.Popen (["find", git_dir + "/objects/pack", "-iname", "pack-*.idx"], stdout = subprocess.PIPE, stderr = subprocess.PIPE, close_fds = True)
    streams = hnd.communicate ();

    if (hnd.returncode == 0):
        for line in streams[0].splitlines ():
            packs.append (line)

    return packs


def get_commits (git_dir):

    commits = []

    hnd = subprocess.Popen (["git", "-C", git_dir, "rev-list", "--all", "--reverse", "--timestamp"], stdout = subprocess.PIPE, stderr = subprocess.PIPE, close_fds = True)
    streams = hnd.communicate ();

    if (hnd.returncode == 0):
        for line in streams[0].splitlines ():
            parts = line.split (None)
            commits.append ({
                'tstamp':   parts[0],
                'id':       parts[1]
            })

    return commits


def get_packed_objects (git_dir, packs):

    global packed_objects

    packed_objects = {}

    m = re.compile (b"[0-9a-f]{40}")

    cmd = ["git", "-C", git_dir, "verify-pack", "-v"]
    cmd.extend (packs)
    hnd = subprocess.Popen (cmd, stdout = subprocess.PIPE, stderr = subprocess.PIPE, close_fds = True)
    streams = hnd.communicate ()

    if (hnd.returncode == 0):
        for line in streams[0].splitlines ():
            parts = line.split (None)
            if (m.match (parts[0])):
                if (parts[0] not in packed_objects):
                    packed_objects[parts[0]] = parts


def get_unpacked_size (git_dir, object_id):

    object_size = 0

    hnd = subprocess.Popen (["git", "-C", git_dir, "cat-file", "-s", object_id], stdout = subprocess.PIPE, stderr = subprocess.PIPE, close_fds = True)
    streams = hnd.communicate ();

    if (hnd.returncode == 0):
        object_size = int (streams[0])
    else:
        log_write ("# ERROR: git-cat-file failed (object_id: " + object_id.decode() + ")")

    return object_size


def get_commit_tree (git_dir, commit_id):

    objects = []

    hnd = subprocess.Popen (["git", "-C", git_dir, "cat-file", "-p", commit_id], stdout = subprocess.PIPE, stderr = subprocess.PIPE, close_fds = True)
    streams = hnd.communicate ();

    if (hnd.returncode == 0):
        line = streams[0].splitlines ().pop (0)
        parts = line.split (None)
        if (parts[0] == b"tree"):
            objects.append ({
                'type': parts[0],
                'id':   parts[1]
            })
        else:
            log_write ("# ERROR: cannot find a tree from commit")
    else:
        log_write ("# ERROR: git-cat-file failed (commit_id: " + commit_id.decode() + ")")

    return objects


def get_tree_objects (git_dir, tree_id):

    objects = []

    hnd = subprocess.Popen (["git", "-C", git_dir, "cat-file", "-p", tree_id], stdout = subprocess.PIPE, stderr = subprocess.PIPE, close_fds = True)
    streams = hnd.communicate ();

    if (hnd.returncode == 0):
        for line in streams[0].splitlines ():
            parts = line.split (None)
            objects.append ({
                'type': parts[1],
                'id':   parts[2]
            })
    else:
        log_write ("# ERROR: git-cat-file failed (tree_id: " + tree_id.decode() + ")")

    return objects


###############################################################################


### Parsing functions ######################################################

def get_object_size (size, git_dir, object_id):

    object_size = 0

    if (object_id in packed_objects):
        object_size = int (packed_objects[object_id][3])
        size['packed'] = size['packed'] + object_size
    else:
        object_size = get_unpacked_size (git_dir, object_id)
        size['unpacked'] = size['unpacked'] + object_size

    return object_size


def object_seen (object_id):

    global seen_objects

    if (object_id in seen_objects):
        return True
    else:
        seen_objects[object_id] = 1
        return False


def get_recursive_size (size, git_dir, object_type, object_id, state):

    if (object_seen (object_id) == False):

        get_object_size (size, git_dir, object_id)
        state['objects'] = state['objects'] + 1
        # log_write_nln ("# " + str (state['commits']) + "/" + str (state['total_commits']) + " commits done (" + str (state['objects']) + " object(s) found)")

        sub_objects = []
        if (object_type == b"commit"):
            sub_objects = get_commit_tree (git_dir, object_id)
        elif (object_type == b"tree"):
            sub_objects = get_tree_objects (git_dir, object_id)
        elif (object_type != b"blob"):
            log_write ("# WARNING: unknown object type (" + object_type.decode() + ")")

        for sub_object in sub_objects:
            get_recursive_size (size, git_dir, sub_object['type'], sub_object['id'], state)

    return size

###############################################################################


if (len (sys.argv) > 1):
    working_dir = sys.argv[1]
else:
    working_dir = "."

# Git directory...
git_dir = get_git_dir (working_dir);
if (git_dir != ""):
    log_write ("# Repository directory: " + git_dir)
else:
    log_write ("# ERROR: cannot detect repository root directory!")
    sys.exit (1)


# Packed objects...
packs = get_pack_files (git_dir)
if (len (packs) != 0):
    log_write ("# Fetching all packed object sizes...")
    get_packed_objects (git_dir, get_pack_files (git_dir))
else:
    log_write ("# WARNING: cannot find any pack files!")


# Commits...
log_write ("# Fetching all commits...")
commits = get_commits (git_dir)
if (len (commits) == 0):
    log_write ("# ERROR: cannot find any commits!")
    sys.exit (1)


# Hard work...
log_write ("# Fetching all related objects...")

state = { 'objects': 0, 'commits': 0, 'total_commits': len (commits) }
total_packed_size = 0
total_unpacked_size = 0

for commit in commits:
    state['commits'] = state['commits'] + 1
    size = { 'packed': 0, 'unpacked': 0 }
    get_recursive_size (size, git_dir, b"commit", commit['id'], state)
    total_packed_size = total_packed_size + size['packed']
    total_unpacked_size = total_unpacked_size + size['unpacked']

    print (commit['tstamp'].decode() + " " + commit['id'].decode() + " " + str (size['packed'] + size['unpacked']))


# Some stats...
log_write ("# Total packed size: " + str (total_packed_size))
log_write ("# Total unpacked size: " + str (total_unpacked_size))
log_write ("# Total size: " + str (total_packed_size + total_unpacked_size))
