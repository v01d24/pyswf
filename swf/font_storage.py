import json
import os

from typing import Dict, Optional

from lxml import etree
from lxml.objectify import ObjectifiedElement

from swf.svg import Svg


class FontStorage:
    """
        Хранилище шрифтов. Позволяет получать и сохранять символы шрифтов в файлы.
        Имеет структуру:
        - <название шрифта 1>
          - <код символа 1>.svg
          - <код символа 2>.svg
          ...
        - <название шрифта 2>
        ...
    """

    def __init__(self, font_storage_dir: str) -> None:
        self._font_storage_dir = font_storage_dir
        self._fonts = self._get_available_fonts()

    def __getstate__(self):
        return {
            '_font_storage_dir': self._font_storage_dir
        }

    def __setstate__(self, state):
        self._font_storage_dir = state['_font_storage_dir']
        self._fonts = self._get_available_fonts()

    def _get_available_fonts(self) -> Dict[str, 'Font']:
        fonts = {}
        if not os.path.exists(self._font_storage_dir):
            return fonts
        for filename in os.listdir(self._font_storage_dir):
            font_dir = os.path.join(self._font_storage_dir, filename)
            fonts[filename] = Font(font_dir)
        return fonts

    def get_or_create_font(self, font_name: str) -> 'Font':
        font = self._fonts.get(font_name)
        if font is not None:
            return font
        font_path = self._get_font_path(font_name)
        font = Font(font_path)
        self._fonts[font_name] = font
        return font

    def _get_font_path(self, font_name: str) -> str:
        return os.path.join(self._font_storage_dir, font_name)


class Font:
    def __init__(self, font_dir: str) -> None:
        self._font_dir = font_dir
        self._glyph_paths = self._get_available_glyph_paths()
        self._glyphs = {}
        self._glyph_advances = self._read_advances()

    def __getstate__(self):
        return {
            '_font_dir': self._font_dir
        }

    def __setstate__(self, state):
        self._font_dir = state['_font_dir']
        self._glyph_paths = self._get_available_glyph_paths()
        self._glyphs = {}
        self._glyph_advances = self._read_advances()

    def _get_available_glyph_paths(self) -> Dict[int, str]:
        glyph_paths = {}
        if not os.path.exists(self._font_dir):
            return glyph_paths
        for filename in os.listdir(self._font_dir):
            if not filename.endswith('.svg'):
                continue
            filename_without_extension = filename[:-4]
            if not filename_without_extension.isdigit():
                continue
            code = int(filename_without_extension)
            glyph_path = os.path.join(self._font_dir, filename)
            glyph_paths[code] = glyph_path
        return glyph_paths

    def _read_advances(self) -> Dict[int, int]:
        advances_path = self._get_advances_path()
        if not os.path.exists(advances_path):
            return {}
        with open(advances_path, 'rt') as f:
            return json.loads(f.read())

    def add_glyph(self, code: int, elem: ObjectifiedElement) -> None:
        if code in self._glyph_paths:
            return
        e = Svg.create_element_maker()
        svg = e.svg(version=Svg.SVG_VERSION)
        svg.append(elem)
        serialized_svg = etree.tostring(svg, encoding='utf-8', xml_declaration=True)
        if not os.path.exists(self._font_dir):
            os.makedirs(self._font_dir)
        filename = '{}.svg'.format(code)
        glyph_path = os.path.join(self._font_dir, filename)
        with open(glyph_path, 'wb') as f:
            f.write(serialized_svg)
        self._glyph_paths[code] = glyph_path
        self._glyphs[code] = elem

    def add_glyph_advance(self, code: int, advance: int) -> None:
        if advance is not None and code not in self._glyph_advances:
            self._glyph_advances[code] = advance

    def get_glyph(self, code: int) -> Optional[ObjectifiedElement]:
        elem = self._glyphs.get(code)
        if elem is not None:
            return elem
        glyph_path = self._glyph_paths.get(code)
        if glyph_path is None:
            return None
        with open(glyph_path, 'rt') as f:
            svg = etree.parse(f)
        elem = svg.getroot().find('path')
        self._glyphs[code] = elem
        return elem

    def get_glyph_advance(self, code: int) -> Optional[int]:
        return self._glyph_advances.get(code)

    def has_glyph(self, code):
        return code in self._glyph_paths

    def save_advances(self) -> None:
        advances_path = self._get_advances_path()
        with open(advances_path, 'wt') as f:
            f.write(json.dumps(self._glyph_advances))

    def _get_advances_path(self) -> str:
        return os.path.join(self._font_dir, 'advances.json')
