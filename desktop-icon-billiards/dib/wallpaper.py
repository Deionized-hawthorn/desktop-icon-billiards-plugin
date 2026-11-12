"""Read the Windows wallpaper and render its placement on the primary display."""
import ctypes
from ctypes import wintypes

import comtypes
import comtypes.client
from PIL import Image, ImageOps

from .shell import ShellDesktop


class IDesktopWallpaper(comtypes.IUnknown):
    _iid_ = comtypes.GUID('{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}')
    _methods_ = []


def _wallpaper_string(service, slot, kind, value):
    address = ctypes.c_void_p()
    try:
        ShellDesktop._invoke(service, slot, [kind, ctypes.POINTER(ctypes.c_void_p)],
                             value, ctypes.byref(address))
        return ctypes.wstring_at(address) if address else ''
    finally:
        ctypes.windll.ole32.CoTaskMemFree(address)


def _render(image, position, color, screen, desktop):
    left, top, right, bottom = screen
    size = right - left, bottom - top
    if position == 2:  # Stretch
        return image.resize(size, Image.Resampling.LANCZOS)
    if position == 4:  # Fill
        return ImageOps.fit(image, size, Image.Resampling.LANCZOS)
    if position == 5:  # Span
        x, y, end_x, end_y = desktop
        span = ImageOps.fit(image, (end_x - x, end_y - y), Image.Resampling.LANCZOS)
        return span.crop((left - x, top - y, right - x, bottom - y))
    if position == 3:  # Fit
        image = ImageOps.contain(image, size, Image.Resampling.LANCZOS)

    canvas = Image.new('RGB', size, color)
    if position == 1:  # Tile from the virtual desktop origin.
        start_x = (desktop[0] - left) % image.width - image.width
        start_y = (desktop[1] - top) % image.height - image.height
        for y in range(start_y, size[1], image.height):
            for x in range(start_x, size[0], image.width):
                canvas.paste(image, (x, y))
    else:  # Center, or the letterboxed Fit image.
        canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def primary_wallpaper(screen, desktop):
    """Return the displayed image, or None when Windows supplies no readable wallpaper."""
    try:
        service = comtypes.client.CreateObject(
            '{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}', interface=IDesktopWallpaper)
        count = wintypes.UINT()
        ShellDesktop._invoke(service, 6, [ctypes.POINTER(wintypes.UINT)], ctypes.byref(count))
        for index in range(count.value):
            monitor = _wallpaper_string(service, 5, wintypes.UINT, index)
            rect = wintypes.RECT()
            ShellDesktop._invoke(service, 7, [wintypes.LPCWSTR, ctypes.POINTER(wintypes.RECT)],
                                 monitor, ctypes.byref(rect))
            if (rect.left, rect.top, rect.right, rect.bottom) == screen:
                break
        else:
            return None

        path = _wallpaper_string(service, 4, wintypes.LPCWSTR, monitor)
        if not path:
            return None
        position, color = ctypes.c_int(), wintypes.DWORD()
        ShellDesktop._invoke(service, 11, [ctypes.POINTER(ctypes.c_int)], ctypes.byref(position))
        ShellDesktop._invoke(service, 9, [ctypes.POINTER(wintypes.DWORD)], ctypes.byref(color))
        rgb = tuple((color.value >> shift) & 255 for shift in (0, 8, 16))
        with Image.open(path) as source:
            return _render(ImageOps.exif_transpose(source).convert('RGB'), position.value, rgb, screen, desktop)
    except (OSError, comtypes.COMError, ValueError, Image.DecompressionBombError):
        # Custom wallpaper providers can leave no readable image; keep the existing clear felt.
        return None
