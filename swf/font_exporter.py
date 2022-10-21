from typing import Optional, Dict

from lxml.objectify import ObjectifiedElement

from swf.consts import EM_SQUARE_LENGTH
from swf.data import SWFShape
from swf.font_storage import FontStorage, Font
from swf.svg import Svg
from swf.tag import TagDefineFont, TagDefineFont2


class FontExporter:
    def __init__(self, parent_elem: ObjectifiedElement, font_storage: FontStorage) -> None:
        self._parent_elem = parent_elem
        self._font_storage = font_storage
        self._e = Svg.create_element_maker()
        self._glyph_exporters = {}
        self._next_font_id = 1000

    def export_font(self, font_tag: TagDefineFont) -> None:
        if isinstance(font_tag, TagDefineFont2):
            code_table = {code: index for index, code in enumerate(font_tag.codeTable)}
            font_name = font_tag.fontName
        else:
            code_table = {}
            font_name = 'Font {}'.format(font_tag.characterId)
        font_elem = self._add_font_element(font_tag.characterId)
        font = self._font_storage.get_or_create_font(font_name)
        glyph_exporter = GlyphExporter(font_tag.characterId, code_table, font_elem, font)
        self._glyph_exporters[font_tag.characterId] = glyph_exporter
        for index, glyph in enumerate(font_tag.glyphShapeTable):
            glyph_exporter.export_glyph(index, glyph)

    def export_glyph_by_code(self, font_tag: TagDefineFont2, code: int) -> Optional[int]:
        glyph_exporter = self._glyph_exporters.get(font_tag.characterId)
        if glyph_exporter is not None:
            return glyph_exporter.export_glyph_by_code(code)
        font_elem = self._add_font_element(self._next_font_id)
        font = self._font_storage.get_or_create_font(font_tag.fontName)
        glyph_exporter = GlyphExporter(self._next_font_id, {}, font_elem, font)
        self._glyph_exporters[font_tag.characterId] = glyph_exporter
        self._next_font_id += 1
        return glyph_exporter.export_glyph_by_code(code)

    def _add_font_element(self, font_id: int) -> ObjectifiedElement:
        font_elem = self._e.g(id='font_{}'.format(font_id))
        font_elem.set('data-type', 'font')
        self._parent_elem.append(font_elem)
        return font_elem


class GlyphExporter:
    def __init__(self,
                 font_id: int,
                 code_table: Dict[int, int],
                 font_elem: ObjectifiedElement, font: Font) -> None:
        self._font_id = font_id
        self._code_table = code_table
        self._font_elem = font_elem
        self._font = font
        self._e = Svg.create_element_maker()
        self._next_glyph_index = 0

    def export_glyph(self, index: int, glyph: SWFShape) -> None:
        glyph_elem = self.glyph_to_elem(glyph)
        self._add_glyph_element(index, glyph_elem)
        self._next_glyph_index = max(self._next_glyph_index, index + 1)

    def export_glyph_by_code(self, code: int) -> Optional[int]:
        glyph_index = self._code_table.get(code)
        if glyph_index is not None:
            return glyph_index
        glyph_elem = self._font.get_glyph(code)
        if glyph_elem is None:
            return None
        glyph_index = self._next_glyph_index
        self._add_glyph_element(glyph_index, glyph_elem)
        self._code_table[code] = glyph_index
        self._next_glyph_index += 1
        return glyph_index

    def _add_glyph_element(self, glyph_index: int, glyph_elem: ObjectifiedElement) -> None:
        glyph_elem.set('id', 'font_{}_{}'.format(self._font_id, glyph_index))
        glyph_elem.set('data-type', 'font_glyph')
        glyph_elem.set('transform', 'scale({0})'.format(float(1) / EM_SQUARE_LENGTH))
        self._font_elem.append(glyph_elem)

    def glyph_to_elem(self, glyph: SWFShape) -> Optional[ObjectifiedElement]:
        path_group = glyph.export().g.getchildren()
        if len(path_group) > 0:
            path = path_group[0]
            del path.attrib['stroke']
            del path.attrib['fill']
        else:
            path = self._e.path(d='')
        return path
