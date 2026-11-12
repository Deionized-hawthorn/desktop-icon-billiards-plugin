"""Turn a local portrait into the head of the pocket celebration character."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

HEAD_SIZE = 128
DANCE_SIZE = (168, 178)
DANCE_FPS = 24
DANCE_FRAMES = 24
DANCE_SECONDS = 2.25
PHOTO_FORMATS = ('JPEG', 'PNG', 'WEBP', 'BMP')


def open_photo(path):
    with Image.open(path, formats=PHOTO_FORMATS) as source:
        if source.width * source.height > 64_000_000:
            raise ValueError('照片尺寸过大，请缩小后重新选择。')
        source.draft('RGB', (1024, 1024))
        photo = ImageOps.exif_transpose(source)
        photo.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        if 'A' in photo.getbands() or 'transparency' in photo.info:
            transparent = photo.convert('RGBA')
            photo = Image.new('RGB', photo.size, '#c9e5d7')
            photo.paste(transparent, mask=transparent.getchannel('A'))
        return photo.convert('RGB')


def crop_square(size, center, fraction):
    width, height = size
    side = max(1, min(min(size), round(min(size) * fraction)))
    left = max(0, min(width - side, round(center[0] - side / 2)))
    top = max(0, min(height - side, round(center[1] - side / 2)))
    return left, top, left + side, top + side


def cartoon_head(photo, crop):
    """Simplify colors and ink facial contours inside a rounded portrait."""
    size = (HEAD_SIZE, HEAD_SIZE)
    portrait = photo.crop(crop).resize(size, Image.Resampling.LANCZOS)
    smooth = portrait.filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(.8))
    vivid = ImageEnhance.Color(smooth).enhance(1.3)
    vivid = ImageEnhance.Contrast(vivid).enhance(1.06)
    colors = vivid.quantize(22, dither=Image.Dither.NONE).convert('RGB')
    edges = vivid.convert('L').filter(ImageFilter.FIND_EDGES).point(
        lambda level: min(185, max(0, (level - 12) * 5)))
    portrait = Image.composite(Image.new('RGB', size, '#292537'), colors, edges).convert('RGBA')
    mask = Image.new('L', size)
    ImageDraw.Draw(mask).ellipse((3, 2, HEAD_SIZE - 4, HEAD_SIZE - 3), fill=255)
    portrait.putalpha(mask.filter(ImageFilter.GaussianBlur(.55)))
    return portrait


def load_avatar(path):
    try:
        with Image.open(path, formats=('PNG',)) as head:
            if head.size == (HEAD_SIZE, HEAD_SIZE):
                return head.convert('RGBA')
    except (OSError, ValueError, Image.DecompressionBombError):
        pass
    return None


def save_avatar(path, head):
    if head is None:
        path.unlink(missing_ok=True)
        return
    temporary = path.with_suffix('.tmp')
    try:
        head.save(temporary, format='PNG')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def dance_pose(seconds):
    return int(max(0., seconds) * DANCE_FPS) % DANCE_FRAMES


class PocketDance:
    def __init__(self):
        self.reset()

    def reset(self):
        self.started = self.until = 0.

    def score(self, now):
        if now >= self.until:
            self.started = now
        self.until = now + DANCE_SECONDS

    def pose_at(self, now):
        if now < self.until:
            return dance_pose(now - self.started)
        return None


def dance_frame(head, pose):
    """Draw an antialiased dance pose with a tilted head and articulated limbs."""
    phase = 2 * math.pi * pose / DANCE_FRAMES
    sway = math.sin(phase)
    bounce = 5 * (1 - math.cos(phase * 2))
    hip_x, hip_y = 84 + 8 * sway, 119 - bounce
    shoulder_x, shoulder_y = hip_x + 4 * sway, hip_y - 28
    scale = 2
    frame = Image.new('RGBA', tuple(length * scale for length in DANCE_SIZE))
    draw = ImageDraw.Draw(frame)
    ink = '#152233'
    sleeve = '#38b69f'

    def dot(x, y, radius, fill):
        draw.ellipse(tuple(value * scale for value in (x - radius, y - radius, x + radius, y + radius)), fill=fill)

    def stroke(points, width, fill):
        draw.line([(x * scale, y * scale) for x, y in points], fill=fill,
                  width=round(width * scale), joint='curve')
        for x, y in points:
            dot(x, y, width / 2, fill)

    draw.ellipse((93, 314, 245, 338), fill=(5, 16, 19, 100))
    for side in (-1, 1):
        step = side * sway
        hip = (hip_x + side * 8, hip_y)
        knee = (hip_x + side * (16 + 7 * step), hip_y + 19 - 4 * step)
        shoe = (hip_x + side * (20 + 13 * step), 157 - 10 * max(0, step))
        stroke((hip, knee, shoe), 13, ink)
        stroke((hip, knee, shoe), 8, '#4f6080')
        stroke((shoe, (shoe[0] + side * 8, shoe[1])), 9, '#eef9f1')
        stroke(((shoe[0], shoe[1] + 3), (shoe[0] + side * 8, shoe[1] + 3)), 2, '#9edacc')

        shoulder = (shoulder_x + side * 14, shoulder_y)
        elbow = (shoulder_x + side * (24 + 4 * step), shoulder_y + 6 - 15 * step)
        hand = (shoulder_x + side * (35 - 7 * step), shoulder_y + 8 - 37 * step)
        stroke((shoulder, elbow, hand), 12, ink)
        stroke((shoulder, elbow, hand), 8, sleeve)
        dot(*hand, 6, ink)
        dot(*hand, 4.5, '#fff0c6')

    stroke(((shoulder_x, shoulder_y - 7), (hip_x, hip_y - 1)), 34, ink)
    stroke(((shoulder_x, shoulder_y - 6), (hip_x, hip_y - 1)), 29, '#197e76')
    stroke(((shoulder_x + 5, shoulder_y - 6), (hip_x + 5, hip_y - 1)), 5, '#8de8c6')
    stroke(((shoulder_x, shoulder_y - 11), (shoulder_x, shoulder_y - 23)), 9, '#fff0c6')

    face = head.resize((124, 124), Image.Resampling.LANCZOS)
    border = Image.new('RGBA', face.size, ink)
    border.putalpha(face.getchannel('A').filter(ImageFilter.MaxFilter(7)))
    border.alpha_composite(face)
    face = border.rotate(-12 * sway, Image.Resampling.BICUBIC, expand=True)
    x = round(shoulder_x * scale - face.width / 2)
    y = round((shoulder_y - 38) * scale - face.height / 2)
    frame.alpha_composite(face, (x, y))

    sparks = ((25, 50, '#ffd381'), (140, 37, '#94edd3'), (42, 20, '#94edd3'), (145, 84, '#ffd381'))
    for index, (x, y, color) in enumerate(sparks):
        radius = 2 + 2 * (1 + math.sin(phase + index))
        y += 4 * math.sin(phase + index)
        stroke(((x - radius, y), (x + radius, y)), 1.6, color)
        stroke(((x, y - radius), (x, y + radius)), 1.6, color)
    return frame.resize(DANCE_SIZE, Image.Resampling.LANCZOS)
