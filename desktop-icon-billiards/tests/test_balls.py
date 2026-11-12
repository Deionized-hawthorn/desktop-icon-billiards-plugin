"""Which desktop items become balls, and how the ball count is padded or trimmed."""
import unittest

from dib.balls import MAX_BALLS, MIN_BALLS, ball_summary, fill_sources, item_tier, priority_order

FOLDERS = {r'C:\Users\me\Desktop\docs', r'C:\Users\me\Desktop\games'}


def is_dir(path):
    return path in FOLDERS


def item(name):
    return {'id': name if name.startswith(('::', '\\')) else rf'C:\Users\me\Desktop\{name}'}


class TierTests(unittest.TestCase):
    def test_shortcuts_programs_and_system_icons_come_first(self):
        for name in ('chrome.lnk', 'Setup.EXE', 'site.url', 'app.appref-ms', '::{20D04FE0-3AEA-1069-A2D8-08002B30309D}',
                     r'\server\share\tool.lnk'):
            with self.subTest(name=name):
                self.assertEqual(item_tier(item(name)['id'], is_dir), 0)

    def test_plain_files_then_folders(self):
        self.assertEqual(item_tier(item('notes.txt')['id'], is_dir), 1)
        self.assertEqual(item_tier(item('docs')['id'], is_dir), 2)

    def test_a_filesystem_error_counts_as_a_file(self):
        def broken(path):
            raise OSError('unreachable')
        self.assertEqual(item_tier(item('x.txt')['id'], broken), 1)


class PriorityTests(unittest.TestCase):
    def test_order_is_tier_then_desktop_position(self):
        items = [item(name) for name in ('docs', 'a.txt', 'one.lnk', 'games', 'b.txt', 'two.exe')]
        self.assertEqual(priority_order(items, is_dir), [2, 5, 1, 4, 0, 3])

    def test_trimming_keeps_programs_and_drops_folders_first(self):
        items = [item(f'f{i}.txt') for i in range(30)] + [item('docs'), item('games')]
        items += [item(f'app{i}.lnk') for i in range(25)]
        keep = sorted(priority_order(items, is_dir)[:MAX_BALLS])
        self.assertEqual(len(keep), MAX_BALLS)
        shortcuts = [i for i, entry in enumerate(items) if entry['id'].endswith('.lnk')]
        self.assertTrue(set(shortcuts) <= set(keep))             # all 25 shortcuts stay
        self.assertEqual(len([i for i in keep if i < 30]), 20)   # then 20 plain files
        self.assertFalse({30, 31} & set(keep))                   # both folders are cut


class PaddingTests(unittest.TestCase):
    def test_limits_are_triangular_numbers(self):
        self.assertEqual((MIN_BALLS, MAX_BALLS), (15, 45))

    def test_fill_sources(self):
        self.assertEqual(fill_sources(0), [])
        self.assertEqual(fill_sources(MIN_BALLS), [])
        self.assertEqual(fill_sources(MAX_BALLS), [])
        self.assertEqual(len(fill_sources(4)), MIN_BALLS - 4)
        self.assertEqual(fill_sources(4)[:5], [0, 1, 2, 3, 0])

    def test_summary_text(self):
        self.assertEqual(ball_summary(4, 4, 11), '桌面 4 个图标，复制补到 15 颗')
        self.assertEqual(ball_summary(60, 45, 0), '桌面 60 个图标，取其中 45 颗（优先快捷方式）')
        self.assertEqual(ball_summary(20, 20, 0), '共 20 颗')


if __name__ == '__main__':
    unittest.main()
