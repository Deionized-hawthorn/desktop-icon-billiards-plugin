import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

from dib.avatar import (
    DANCE_SECONDS, DANCE_SIZE, HEAD_SIZE, cartoon_head, crop_square, dance_frame, load_avatar,
    open_photo, save_avatar,
)
from dib.overlay import BilliardsOverlay
from dib.table import BilliardsMotion


class AvatarTests(unittest.TestCase):
    def test_local_photo_becomes_a_saved_head_and_multiple_dance_poses(self):
        with tempfile.TemporaryDirectory() as folder:
            photo_file = Path(folder) / 'photo.jpg'
            portrait = Image.new('RGB', (192, 256), '#b7dce6')
            draw = ImageDraw.Draw(portrait)
            draw.ellipse((48, 45, 144, 151), fill='#cc9479')
            draw.ellipse((67, 85, 77, 95), fill='#48313e')
            draw.ellipse((111, 85, 121, 95), fill='#48313e')
            portrait.save(photo_file)
            original = photo_file.read_bytes()
            photo = open_photo(photo_file)
            head = cartoon_head(photo, crop_square(photo.size, (96, 96), .65))
            self.assertEqual(head.size, (HEAD_SIZE, HEAD_SIZE))
            self.assertEqual(head.getpixel((0, 0))[3], 0)
            avatar_file = Path(folder) / 'avatar.png'
            save_avatar(avatar_file, head)
            loaded = load_avatar(avatar_file)
            self.assertEqual(loaded.tobytes(), head.tobytes())
            start, later = dance_frame(loaded, 0), dance_frame(loaded, 6)
            self.assertEqual(start.size, DANCE_SIZE)
            self.assertNotEqual(start.tobytes(), later.tobytes())
            save_avatar(avatar_file, None)
            self.assertIsNone(load_avatar(avatar_file))
            self.assertEqual(photo_file.read_bytes(), original)

    def test_face_crop_stays_inside_a_portrait_at_the_edges(self):
        self.assertEqual(crop_square((100, 200), (-30, 500), .5), (0, 150, 50, 200))
        self.assertEqual(crop_square((100, 200), (180, -10), 1.), (0, 0, 100, 100))

    def test_icon_pockets_have_independent_dances_and_a_scratch_does_not_trigger_one(self):
        overlay = BilliardsOverlay.__new__(BilliardsOverlay)
        overlay.table = game = BilliardsMotion((0, 0, 1600, 1000), [(64, 64)] * 3)
        overlay.dances = {}
        overlay.dance_keys, overlay.dance_frames, overlay.dance_head = {}, {}, None
        overlay.dance_scale = 1.
        overlay.primary_bounds = game.work_area
        overlay.want_avatar = Image.new('RGBA', (HEAD_SIZE, HEAD_SIZE), '#da9a81')
        overlay.table_windows = {'dance_1': 81, 'dance_4': 84}
        overlay.present, overlay.position_layer = Mock(), Mock()
        game.state = 'rolling'
        game.white.x, game.white.y = game.pockets[0]
        overlay.advance_table(.01, 10.)
        self.assertTrue(game.white_sunk)
        self.assertFalse(overlay.dances)
        game.state = 'rolling'
        game.icons[0].x, game.icons[0].y = game.pockets[1]
        game.icons[1].x, game.icons[1].y = game.pockets[4]
        overlay.advance_table(.01, 11.)
        self.assertEqual(set(overlay.dances), {1, 4})
        overlay.draw_dances(11.)
        locations = {call.args[0]: call.args[2:] for call in overlay.present.call_args_list}
        for pocket, hwnd in ((1, 81), (4, 84)):
            x, y = locations[hwnd]
            px, py = game.pockets[pocket]
            self.assertAlmostEqual(x + DANCE_SIZE[0] / 2, px, delta=1)
            self.assertAlmostEqual(y + DANCE_SIZE[1] / 2, py, delta=1)
        game.state = 'rolling'
        game.icons[2].x, game.icons[2].y = game.pockets[1]
        overlay.advance_table(.01, 12.)
        self.assertEqual(game.state, 'finished')
        with patch('dib.overlay.win32gui.ShowWindow') as hide:
            overlay.draw_dances(11. + DANCE_SECONDS)
            self.assertEqual(set(overlay.dances), {1})
            self.assertEqual(hide.call_args.args[0], 84)
            overlay.draw_dances(12. + DANCE_SECONDS)
            self.assertEqual(hide.call_args.args[0], 81)
        self.assertFalse(overlay.dances)
