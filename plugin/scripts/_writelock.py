# work-map — Copyright (c) 2026 House of Solance. PolyForm Noncommercial 1.0.0. Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)
"""Shared by both writers (pipeline.py and decisions.py): one exclusive lock per real file path, and the
rule that an implicit config may only write inside its own folder."""
import contextlib, hashlib, os, stat, tempfile

try:
    import fcntl
except ImportError:  # no advisory locks on this platform: concurrent writers are not protected
    fcntl = None


@contextlib.contextmanager
def locked(path):
    """Hold one exclusive lock per target file across read, write, parse-back and rollback (no lost updates)."""
    # shortcut: advisory flock on a private temp-dir lock file; fine for cooperating writers on one machine
    if fcntl is None:
        yield
        return
    key = hashlib.sha1(os.path.realpath(path).encode()).hexdigest()[:16]
    lock_dir = _private_lock_dir()
    # no-follow, no truncate, owner-only: a planted symlink or another user's file is refused, never written
    fd = os.open(os.path.join(lock_dir, "write-%s.lock" % key), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if os.fstat(fd).st_uid != os.getuid():
            raise SystemExit("refused: lock file is not yours (%s)" % lock_dir)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _private_lock_dir():
    """A per-user lock folder (0700) under the temp dir; refuses one that is a link or not owned by this user."""
    d = os.path.join(tempfile.gettempdir(), "work-map-locks-%d" % os.getuid())
    try:
        os.mkdir(d, 0o700)
    except FileExistsError:
        pass
    st = os.lstat(d)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or (st.st_mode & 0o077):
        raise SystemExit("refused: lock folder %s is not a private folder of yours" % d)
    return d


def confined(path, base):
    """None if path (symlinks resolved) is a .md file inside base (symlinks resolved); else the reason."""
    real, root = os.path.realpath(path), os.path.realpath(base)
    try:
        inside = os.path.commonpath([real, root]) == root
    except ValueError:
        inside = False
    if inside and real.endswith(".md"):
        return None
    return ("%s resolves to %s, which is outside %s or not a .md file; an implicit config may only write there. "
            "Pass --config to trust this config" % (path, real, root))
