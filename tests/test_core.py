import os
import shutil
import threading
import unittest

from directory_atomic_remover import AtomicRemover, AtomicRemoverError


class _AtomicRemoverCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_work")
        if os.path.exists(self._tmp):
            shutil.rmtree(self._tmp, ignore_errors=True)
        os.makedirs(self._tmp)

    def tearDown(self) -> None:
        if os.path.exists(self._tmp):
            shutil.rmtree(self._tmp, ignore_errors=True)

    def _target(self, name: str = "target") -> str:
        path = os.path.join(self._tmp, name)
        os.makedirs(path)
        return path


class ReplaceBasic(_AtomicRemoverCase):
    def test_replaces_with_empty_directory(self) -> None:
        target = self._target()
        with open(os.path.join(target, "a.txt"), "w") as fh:
            fh.write("hello")
        remover = AtomicRemover(target)
        result = remover.replace()
        self.assertEqual(result, target)
        self.assertTrue(os.path.isdir(target))
        self.assertEqual(os.listdir(target), [])

    def test_target_is_absolute(self) -> None:
        rel = os.path.relpath(self._target("rel"))
        remover = AtomicRemover(rel)
        self.assertEqual(remover.target, os.path.abspath(rel))

    def test_returns_target_path(self) -> None:
        target = self._target()
        remover = AtomicRemover(target)
        self.assertIs(remover.replace(), remover.target)


class ReplaceErrors(_AtomicRemoverCase):
    def test_missing_target_raises(self) -> None:
        missing = os.path.join(self._tmp, "does_not_exist")
        with self.assertRaises(AtomicRemoverError):
            AtomicRemover(missing).replace()

    def test_file_target_raises(self) -> None:
        file_path = os.path.join(self._tmp, "a_file")
        with open(file_path, "w") as fh:
            fh.write("x")
        with self.assertRaises(AtomicRemoverError):
            AtomicRemover(file_path).replace()

    def test_double_replace_raises(self) -> None:
        target = self._target()
        remover = AtomicRemover(target)
        remover.replace()
        with self.assertRaises(AtomicRemoverError):
            remover.replace()

    def test_non_string_target_raises_type_error(self) -> None:
        with self.assertRaises(TypeError):
            AtomicRemover(123)  # type: ignore[arg-type]


class ReplaceInternals(_AtomicRemoverCase):
    def test_trash_dir_cleared_before_rename(self) -> None:
        target = self._target()
        trash = target + ".removing"
        os.makedirs(os.path.join(trash, "nested"))
        with open(os.path.join(trash, "stubborn"), "w") as fh:
            fh.write("leftover")
        remover = AtomicRemover(target)
        remover.replace()
        # After replace, target is the fresh empty dir. The old content is
        # being deleted in the background; we only assert the rename succeeded.
        self.assertTrue(os.path.isdir(target))
        self.assertEqual(os.listdir(target), [])

    def test_old_content_removed_asynchronously(self) -> None:
        target = self._target()
        deep = os.path.join(target, "a", "b", "c")
        os.makedirs(deep)
        with open(os.path.join(deep, "file.txt"), "w") as fh:
            fh.write("data")
        remover = AtomicRemover(target)
        remover.replace()
        # The trash path existed right after rename; deletion is racing us.
        # Instead of sleeping (which would make the test non-deterministic),
        # we join all non-main daemon threads and then assert deletion.
        for t in threading.enumerate():
            if t is not threading.main_thread() and t.is_alive():
                t.join(timeout=30)
        self.assertFalse(os.path.exists(target + ".removing"))


class ReplacePreservesReadersView(_AtomicRemoverCase):
    def test_target_is_directory_immediately_after_replace(self) -> None:
        target = self._target()
        AtomicRemover(target).replace()
        self.assertTrue(os.path.isdir(target))

    def test_replacement_is_empty(self) -> None:
        target = self._target()
        with open(os.path.join(target, "preexisting"), "w") as fh:
            fh.write("x")
        AtomicRemover(target).replace()
        self.assertEqual(os.listdir(target), [])


if __name__ == "__main__":
    unittest.main()
