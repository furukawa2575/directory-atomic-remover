from __future__ import annotations

import os
import shutil
import threading


class AtomicRemoverError(Exception):
    """Raised when the target directory cannot be found or is not a directory."""


class _BackgroundDeleter(threading.Thread):
    """Deletes a leftover directory in a daemon thread.

    Daemons are used because a lingering old tree should never block process
    exit — the OS reclaims the inode either way. If this thread is killed
    mid-delete (process crash, SIGKILL), the renamed tree is orphaned on disk
    and must be cleaned by an external sweep. That is an accepted trade-off:
    readers never block on deletion, but orphans are possible after a hard
    kill.
    """

    def __init__(self, path: str) -> None:
        super().__init__(daemon=True)
        self._path = path

    def run(self) -> None:
        try:
            shutil.rmtree(self._path, ignore_errors=True)
        except Exception:
            # We are inside a daemon thread with no caller to report to.
            # Swallowing is the only sane option; the renamed tree is the
            # canonical source of orphan debris and an external sweep is
            # expected to catch it.
            pass


class AtomicRemover:
    """Rename a directory out of the way and replace it with a fresh one.

    A reader doing ``os.listdir(target)`` either sees the old tree or the
    empty replacement — never a half-deleted intermediate. Deletion of the
    old tree happens in a background daemon thread.

    Design decisions:
      * The replacement directory is always created empty. Callers that
        need pre-populated content should fill it themselves after
        :meth:`replace` returns.
      * Renames are never retried. If the OS rejects the rename (e.g.
        cross-device), the exception surfaces to the caller immediately.
      * Cleanup of any prior leftover from a previous run is best-effort
        and non-fatal.
    """

    def __init__(self, target: str) -> None:
        if not isinstance(target, str):
            raise TypeError("target must be a string path")
        self._target = os.path.abspath(target)
        self._trash_dir = self._target + ".removing"
        self._replaced = False

    @property
    def target(self) -> str:
        """Absolute path of the directory that :meth:`replace` swaps out."""
        return self._target

    def replace(self) -> str:
        """Swap ``target`` for a fresh empty directory.

        Returns the absolute path of the new, empty replacement directory.

        Raises :class:`AtomicRemoverError` if ``target`` does not exist or is
        not a directory. Raises ``OSError`` (or a subclass) if the underlying
        rename or mkdir fails.

        Calling :meth:`replace` twice on the same instance raises
        :class:`AtomicRemoverError`; each replacement needs a fresh remover so
        the instance state cannot drift.
        """
        if self._replaced:
            raise AtomicRemoverError(
                "replace() has already been called on this instance; "
                "create a new AtomicRemover for subsequent replacements"
            )

        if not os.path.isdir(self._target):
            raise AtomicRemoverError(
                f"target does not exist or is not a directory: {self._target!r}"
            )

        # Best-effort cleanup of a leftover from a previous crashed run.
        # Using ignore_errors here (not inside the thread) is deliberate:
        # a leftover that cannot be removed now will almost certainly block
        # the rename below, in which case that OSError is the real signal.
        if os.path.lexists(self._trash_dir):
            shutil.rmtree(self._trash_dir, ignore_errors=True)

        # The atomic heart: rename the live tree aside. On POSIX this is
        # atomic within the same filesystem; a concurrent reader sees either
        # the old name or nothing — never a partial tree.
        os.rename(self._target, self._trash_dir)

        # Create the replacement before kicking off deletion so that the
        # window in which ``target`` does not exist is as short as the mkdir
        # syscall itself.
        os.mkdir(self._target)

        self._replaced = True

        _BackgroundDeleter(self._trash_dir).start()

        return self._target
