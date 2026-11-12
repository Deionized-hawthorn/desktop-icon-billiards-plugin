"""Error dialogs must say where the failure happened, not just what it was."""
import unittest

from dib.ui import describe_error
from dib.update import version_tuple


class DescribeErrorTests(unittest.TestCase):
    def test_reports_the_location_inside_the_package(self):
        try:
            version_tuple('not a version')
        except ValueError as error:
            text = describe_error(error)
        self.assertIn('version must use major.minor.patch', text)
        self.assertIn('update.py:', text)
        self.assertIn('in version_tuple', text)
        self.assertIn('error.log', text)

    def test_falls_back_to_the_last_frame_outside_the_package(self):
        def broken():
            for _ in None:
                pass
        try:
            broken()
        except TypeError as error:
            text = describe_error(error)
        self.assertIn('NoneType', text)
        self.assertIn('in broken', text)

    def test_an_exception_that_was_never_raised_has_no_location(self):
        text = describe_error(RuntimeError('plain'))
        self.assertTrue(text.startswith('plain'))
        self.assertNotIn('出错位置', text)


if __name__ == '__main__':
    unittest.main()
