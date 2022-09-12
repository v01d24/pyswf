import argparse
import traceback

from swf.font_exporter import GlyphExporter
from swf.font_storage import FontStorage
from swf.tag import TagDefineFont2
from swf.movie import SWF
from arg_utils import add_source_args, get_source_paths


class FontExtractor(object):
    def __init__(self, font_storage):
        self._font_storage = font_storage

    def extract_fonts(self, file_path):
        with open(file_path, 'rb') as f:
            swf = SWF(f)
        for tag in swf.tags:
            if isinstance(tag, TagDefineFont2):
                self._extract_tag_font(tag)

    def _extract_tag_font(self, font_tag):
        font = self._font_storage.get_or_create_font(font_tag.fontName)
        for code, glyph in zip(font_tag.codeTable, font_tag.glyphShapeTable):
            if font.has_glyph(code):
                continue
            elem = GlyphExporter.glyph_to_elem(glyph)
            if elem is not None:
                font.add_glyph(code, elem)
        if font_tag.hasLayout:
            for code, advance in zip(font_tag.codeTable, font_tag.fontAdvanceTable):
                font.add_glyph_advance(code, advance)
            font.save_advances()


def parse_args():
    parser = argparse.ArgumentParser(description='Extract fonts from SWF to font store')
    add_source_args(parser)
    parser.add_argument('--out', dest='dir_out', type=str, required=True,
                        help='Path to a font storage directory')
    return parser.parse_args()


def extract_fonts(paths, font_storage_dir):
    font_storage = FontStorage(font_storage_dir)
    font_extractor = FontExtractor(font_storage)
    for path in paths:
        print(path)
        try:
            font_extractor.extract_fonts(path)
        except KeyboardInterrupt:
            break
        except:
            print(traceback.format_exc())


if __name__ == '__main__':
    args = parse_args()
    source_paths = get_source_paths(args)
    extract_fonts(source_paths, args.dir_out)
