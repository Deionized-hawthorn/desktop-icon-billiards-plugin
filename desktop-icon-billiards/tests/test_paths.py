"""The runtime directory must survive a broken temp directory."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dib import paths


class RuntimeDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def environment(self, **values):
        base = {name: str(self.root / name) for name in ('LOCALAPPDATA', 'APPDATA')}
        base.update(values)
        return mock.patch.dict(os.environ, base, clear=False)

    def test_uses_the_temp_directory_when_it_works(self):
        temp = self.root / 'temp'
        temp.mkdir()
        with self.environment(), mock.patch.object(paths, '_temporary_directory', return_value=temp):
            directory = paths.runtime_directory()
        self.assertEqual(directory, temp / paths.RUNTIME_DIRECTORY_NAME)
        self.assertTrue(directory.is_dir())
        self.assertFalse((directory / '.write-test').exists())  # the probe file is cleaned up

    def test_falls_back_to_the_profile_when_temp_cannot_hold_a_folder(self):
        broken = self.root / 'temp-is-a-file'
        broken.write_text('x')  # a file where the directory should be: mkdir fails
        with self.environment(), mock.patch.object(paths, '_temporary_directory', return_value=broken):
            directory = paths.runtime_directory()
        self.assertEqual(directory, self.root / 'LOCALAPPDATA' / paths.RUNTIME_DIRECTORY_NAME)
        self.assertTrue(directory.is_dir())

    def test_falls_back_when_the_temp_lookup_itself_fails(self):
        with self.environment(), mock.patch.object(paths, '_temporary_directory', side_effect=OSError('no temp')):
            directory = paths.runtime_directory()
        self.assertEqual(directory.parent.name, 'LOCALAPPDATA')

    def test_uses_roaming_data_when_local_data_is_missing(self):
        with self.environment(LOCALAPPDATA=''), \
                mock.patch.object(paths, '_temporary_directory', side_effect=OSError('no temp')):
            directory = paths.runtime_directory()
        self.assertEqual(directory.parent.name, 'APPDATA')

    def test_raises_a_clear_error_when_nothing_is_usable(self):
        with self.environment(LOCALAPPDATA='', APPDATA=''), \
                mock.patch.object(paths, '_temporary_directory', side_effect=OSError('no temp')):
            with self.assertRaises(OSError) as caught:
                paths.runtime_directory()
        self.assertIn('运行目录', str(caught.exception))

    def test_the_parent_and_the_watchdog_agree_on_the_fallback(self):
        broken = self.root / 'temp-is-a-file'
        broken.write_text('x')
        with self.environment(), mock.patch.object(paths, '_temporary_directory', return_value=broken):
            self.assertEqual(paths.runtime_directory(), paths.runtime_directory())


if __name__ == '__main__':
    unittest.main()
