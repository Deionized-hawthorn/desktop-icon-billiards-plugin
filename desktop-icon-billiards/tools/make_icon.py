"""Build the Windows ICO from the checked-in PNG master."""

from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / 'assets'
PNG_PATH = ASSETS / 'desktop-icon-billiards.png'
ICO_PATH = ASSETS / 'desktop-icon-billiards.ico'
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> None:
    with Image.open(PNG_PATH) as source:
        icon = source.convert('RGBA')
    if icon.width != icon.height or icon.width < max(ICO_SIZES):
        raise ValueError(f'{PNG_PATH.name} must be square and at least 256 px wide')

    icon.save(ICO_PATH, sizes=[(size, size) for size in ICO_SIZES], bitmap_format='bmp')
    print(f'wrote {ICO_PATH.name} ({", ".join(map(str, ICO_SIZES))})')


if __name__ == '__main__':
    main()
