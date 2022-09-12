from __future__ import absolute_import
import argparse
import os
import traceback

from typing import Optional, List

from arg_utils import add_source_args, get_source_paths
from swf.font_storage import FontStorage
from swf.movie import SWF
from swf.export import SVGExporter, FrameSVGExporterMixin


class FrameSVGExporter(FrameSVGExporterMixin, SVGExporter):
    pass


class Converter:
    def __init__(self, font_storage: FontStorage) -> None:
        self._exporter = FrameSVGExporter(font_storage)

    def convert(self, path_in: str, dir_out: str, frame: Optional[int]) -> None:
        with open(path_in, 'rb') as f_in:
            swf = SWF(f_in)

        frame_count = swf.header.frame_count
        if frame is None and frame_count == 1:
            frame = 0
        if frame is not None and frame >= frame_count:
            frame = frame_count - 1

        if not os.path.exists(dir_out):
            os.mkdir(dir_out)
        filename = os.path.basename(path_in)
        filename_without_extension = filename.rsplit('.', 1)[0]

        if frame is not None:
            svg_filename = '{}.svg'.format(filename_without_extension)
            self.export_svg(swf, frame, dir_out, svg_filename)
            return

        file_dir_out = os.path.join(dir_out, filename_without_extension)
        if not os.path.exists(file_dir_out):
            os.mkdir(file_dir_out)
        for frame in range(0, frame_count):
            svg_filename = '{}.svg'.format(frame + 1)
            self.export_svg(swf, frame, file_dir_out, svg_filename)

    def export_svg(self, swf: SWF, frame: int, dir_out: str, filename: str) -> None:
        path_out = os.path.join(dir_out, filename)
        svg = self._exporter.export(swf, frame)
        with open(path_out, 'wb') as f_out:
            f_out.write(svg)


def parse_args():
    parser = argparse.ArgumentParser(description='Convert an SWF file into an SVG')
    add_source_args(parser)
    parser.add_argument('--out', dest='dir_out', type=str, required=True,
                        help='Path to a font storage directory')
    parser.add_argument('--frame', type=int,
                        help='Export frame FRAME (0-based index) instead of frame 0', required=False)
    parser.add_argument('--fonts', dest='fonts', type=str, required=False,
                        help='Path to a font storage directory')
    return parser.parse_args()


def convert_files(paths: List[str], dir_out: str, frame: Optional[int]) -> None:
    font_storage = FontStorage('fonts')
    converter = Converter(font_storage)
    for path in paths:
        print(path)
        try:
            converter.convert(path, dir_out, frame)
        except KeyboardInterrupt:
            break
        except:
            print(traceback.format_exc())


if __name__ == '__main__':
    args = parse_args()
    source_paths = get_source_paths(args)
    convert_files(source_paths, args.dir_out, args.frame)
