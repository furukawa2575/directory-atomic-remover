# directory-atomic-remover

Renames a target directory out of the way, deletes it in a background thread, and leaves an empty replacement in its place so readers never observe a half-removed tree.

```python
import os
import tempfile
from directory_atomic_remover import AtomicRemover

target = os.path.join(tempfile.mkdtemp(), "mydir")
os.makedirs(target)
# ...write files into target...
remover = AtomicRemover(target)
new_path = remover.replace()   # target is now a fresh, empty dir
# populate new_path here; the old tree is being deleted in the background
```

## Why

A naive ``shutil.rmtree(target)`` leaves the directory visible while files are deleted one by one; a concurrent reader can see a partial tree mid-sweep. This library sidesteps that by renaming the live tree aside first (a single atomic operation on POSIX within the same filesystem) and immediately creating an empty replacement, so the public path always points to a complete directory — either the old one or the new empty one.

The trade-off: deletion runs in a daemon thread and is fire-and-forget. If the process is killed hard (SIGKILL, crash) during that background delete, the renamed ``<target>.removing`` directory is orphaned on disk and must be reclaimed by an external sweep. The library cleans up a pre-existing ``.removing`` leftover at the start of each ``replace()`` on a best-effort basis, but it cannot recover debris from a kill that happens mid-delete.

## Edge cases

- ``replace()`` raises ``AtomicRemoverError`` if the target is missing or not a directory, and again if called twice on the same instance — each replacement needs a fresh ``AtomicRemover``.
- The rename is not retried. If ``target`` and ``.removing`` somehow land on different filesystems, the resulting ``OSError`` surfaces directly to the caller.
- The replacement directory is always empty. If you need it pre-populated, fill it yourself after ``replace()`` returns.

## Example

The example above creates the target directory with ``os.makedirs`` before passing it to ``AtomicRemover``. If the path does not exist, ``replace()`` raises ``AtomicRemoverError``.

## Performance

The window keeps a bounded buffer, so `push` is constant time and memory does not
grow with the length of the stream. `peak` and `trough` are linear in the window
size, which is the trade that keeps `push` cheap.

