import argparse
import os.path
import traceback
from collections import defaultdict
from typing import NamedTuple, List, Set, Iterable, Optional

from lxml.etree import _Element

from arg_utils import add_source_args, get_source_paths
from swf.svg import Svg, ContainerGroup, DisplayGroup, ShapeGroup, TextGroup, Path, Rect, Command, MoveTo, LineTo, \
    LinearGradient


class TextGroupInfo(NamedTuple):
    display_group: DisplayGroup
    text_group: TextGroup
    x: float
    y: float


class PathSignature:
    def __init__(self, **kwargs) -> None:
        self._kwargs = kwargs

    def get_hash(self) -> int:
        return hash(frozenset(self._kwargs.items()))

    def match(self, path: Path) -> bool:
        for key, value in self._kwargs.items():
            if path.elem.get(key) != value:
                return False
        return True


class SvgCleaner:
    ARROW_PARTS_FILL_COLORS = {'#050101', '#090304', '#666666', '#696b6d', '#999999', '#a0a2a5', '#cccccc'}
    ARROW_PARTS_STROKE_COLORS = {'#d0d2d3', '#cccccc'}

    def __init__(self):
        self._text_groups_by_y = None
        self._frame_remover = None

    def clean(self, path_in: str, dir_out: str) -> None:
        self._text_groups_by_y = defaultdict(list)
        svg = Svg.parse(path_in)
        self._frame_remover = FrameRemover(svg.view_box, 10)
        root_group = svg.get_root_group()
        self._clean_groups(root_group)
        self._clean_split_text(root_group)
        self._remove_arrows(svg.root_elem)
        filename = os.path.basename(path_in)
        if not os.path.exists(dir_out):
            os.mkdir(dir_out)
        path_out = os.path.join(dir_out, filename)
        svg.save(path_out)

    def _clean_groups(self, container_group: ContainerGroup):
        display_groups_to_remove = []
        for display_group in container_group.get_display_groups():
            definition = display_group.get_definition()
            if isinstance(definition, ContainerGroup):
                self._clean_groups(definition)
                continue
            should_delete = False
            if isinstance(definition, ShapeGroup):
                should_delete = self._clean_shape(definition)
            elif isinstance(definition, TextGroup):
                should_delete = self._clean_text(display_group, definition)
            if should_delete:
                display_groups_to_remove.append(display_group)
                continue
        for display_group in display_groups_to_remove:
            container_group.remove(display_group)

    def _clean_shape(self, shape_group: ShapeGroup) -> bool:
        if self._is_logo_shape(shape_group):
            return True
        self._clean_shape_paths(shape_group)
        return False

    @classmethod
    def _is_logo_shape(cls, shape_group: ShapeGroup) -> bool:
        paths = shape_group.get_paths()
        if len(paths) != 1:
            return False
        return cls._is_logo_path(paths[0], shape_group.bounds)

    def _clean_shape_paths(self, shape_group: ShapeGroup) -> None:
        paths_to_remove = []
        for path in shape_group.get_paths():
            if self._is_logo_path(path) or self._is_logo_letter_gradient_path(path):
                paths_to_remove.append(path)
                continue
            self._frame_remover.remove_frames(path)
        for path in paths_to_remove:
            shape_group.remove_path(path)

    @staticmethod
    def _is_logo_path(path: Path, bounds: Optional[Rect] = None) -> bool:
        if bounds is None:
            bounds = path.bounds
        width = bounds.get_width()
        height = bounds.get_height()
        is_haval_logo_size = int(width) == 88 and int(height) == 20
        is_wey_logo_size = int(width) == 81 and int(height) in (13, 17)
        if not is_haval_logo_size and not is_wey_logo_size:
            return False
        if bounds.x_min < 470 or bounds.y_min < 380:
            return False
        fill = path.elem.get('fill')
        return fill is not None and fill.startswith('url(#pat')

    @staticmethod
    def _is_logo_letter_gradient_path(path: Path) -> bool:
        filling = path.get_filling()
        if not isinstance(filling, LinearGradient):
            return False
        stop_elements = filling.elem.getchildren()
        if len(stop_elements) == 12:
            if stop_elements[0].get('stop-color') != '#9f9fa0':
                return False
            if stop_elements[-1].get('stop-color') != '#3e3a39':
                return False
            return True
        if len(stop_elements) == 7:
            if stop_elements[0].get('stop-color') != '#c8c9c9':
                return False
            if stop_elements[-1].get('stop-color') != '#3e3a39':
                return False
            return True
        return False

    def _clean_text(self, display_group: DisplayGroup, text_group: TextGroup) -> bool:
        text_size = text_group.get_font_size() or text_group.get_font_size_max()
        if text_size is None:  # пустой текст
            return False
        text_width = text_group.bounds.get_width()
        if text_size >= 14 and text_width >= 200:  # заголовки, подписи
            return True
        if text_size <= 14 and text_width < 280:  # артикул
            return False
        text_length = text_group.get_text_length()
        if text_length == 1 and text_group.bounds is not None:
            # текст может быть разделён по символам, поэтому текстовые объекты с одним символом
            # группируются по координате y, чтобы потом объединить в строки
            text_group_info = TextGroupInfo(
                display_group=display_group,
                text_group=text_group,
                x=text_group.matrix.tx,
                y=text_group.matrix.ty
            )
            self._text_groups_by_y[text_group_info.y].append(text_group_info)
        if text_length <= 2:  # число
            return False
        return True

    def _clean_split_text(self, root_group: ContainerGroup) -> None:
        text_groups_to_remove = []
        for key, grouped_info in self._text_groups_by_y.items():
            if len(grouped_info) < 4:
                continue
            grouped_info = sorted(grouped_info, key=lambda i: i.x)
            prev_x = grouped_info[0].x
            text_groups_in_a_line = [grouped_info[0]]
            for text_group_info in grouped_info[1:]:
                is_line_break = False
                font_size = text_group_info.text_group.get_font_size()
                if font_size is None:
                    is_line_break = True
                min_char_width = font_size / 2.0
                x = text_group_info.x
                dx = x - prev_x
                chars = int((dx + 0.1) / min_char_width)
                if chars < 1 or chars > 3:
                    is_line_break = True
                remainder = dx - chars * min_char_width
                if remainder > 0.1:
                    is_line_break = True
                if is_line_break:
                    if len(text_groups_in_a_line) >= 4:
                        text_groups_to_remove.extend(text_groups_in_a_line)
                    text_groups_in_a_line = []
                prev_x = x
                text_groups_in_a_line.append(text_group_info)
            if len(text_groups_in_a_line) >= 4:
                text_groups_to_remove.extend(text_groups_in_a_line)
        for text_group_info in text_groups_to_remove:
            root_group.remove(text_group_info.display_group)

    def _remove_arrows(self, root_elem: _Element) -> None:
        elements_to_remove = set()
        for path_elem in root_elem.iterfind('.//{http://www.w3.org/2000/svg}path[@fill="#cccccc"]'):
            elements_to_remove.update(self._get_arrow_parts(path_elem))
        for path_elem in elements_to_remove:
            path_elem.getparent().remove(path_elem)

    @classmethod
    def _get_arrow_parts(cls, path_elem: _Element) -> List[_Element]:
        matched_elements = [path_elem]
        prev_elem = path_elem.getprevious()
        while prev_elem is not None and cls._can_be_arrow_part(prev_elem):
            matched_elements.append(prev_elem)
            prev_elem = prev_elem.getprevious()
        next_elem = path_elem.getnext()
        while next_elem is not None and cls._can_be_arrow_part(next_elem):
            matched_elements.append(next_elem)
            next_elem = next_elem.getnext()
        if 4 <= len(matched_elements) <= 12:
            return matched_elements
        return []

    @classmethod
    def _can_be_arrow_part(cls, path_elem: _Element) -> bool:
        if path_elem.get('fill') in cls.ARROW_PARTS_FILL_COLORS:
            return True
        return path_elem.get('fill') == 'none' and path_elem.get('stroke') in cls.ARROW_PARTS_STROKE_COLORS


class FrameRemover:
    LINE_FLAG_IN_INNER_FRAME_BOUNDS = 1
    LINE_FLAG_IN_OUTER_FRAME_BOUNDS = 2
    LINE_FLAG_OUT_OF_FRAME_BOUNDS = 4
    LINE_FLAG_CONTAINS_CURVES = 8

    LINE_FLAG_BOUNDS_MASK = 7

    def __init__(self, frame_rect: Rect, border_width: float) -> None:
        self._inner_frame_bounds = inner_bounds = frame_rect.grow(-border_width / 2)
        self._outer_frame_bounds = outer_bounds = frame_rect.grow(border_width / 2)
        self._frame_line_bounds = [
            Rect(outer_bounds.x_min, outer_bounds.y_min, outer_bounds.x_max, inner_bounds.y_min),
            Rect(outer_bounds.x_min, inner_bounds.y_max, outer_bounds.x_max, outer_bounds.y_max),
            Rect(outer_bounds.x_min, outer_bounds.y_min, inner_bounds.x_min, outer_bounds.y_max),
            Rect(inner_bounds.x_max, outer_bounds.y_min, outer_bounds.x_max, outer_bounds.y_max)
        ]

    def remove_frames(self, path: Path) -> None:
        if path.has_filling():
            return
        commands = path.get_commands()
        filtered_commands = []
        for line_commands in self._iter_line_commands(commands):
            if not self._is_frame(line_commands):
                filtered_commands.extend(line_commands)
        path.set_commands(filtered_commands)

    @staticmethod
    def _iter_line_commands(commands: List[Command]) -> Iterable[List[Command]]:
        """
            Разбиение списка команд по непрерывным линиям
        """
        line_commands = []
        for command in commands:
            if isinstance(command, MoveTo):
                if len(line_commands) > 0:
                    yield line_commands
                line_commands = []
            line_commands.append(command)
        if len(line_commands) > 0:
            yield line_commands

    def _is_frame(self, line_commands: List[Command]) -> bool:
        """
            Метод проверяет, является ли последовательность точек рамкой.
            Алгоритм:
            1) Проверяется, что последовательность содержит не менее 5 точек (4 точки прямоугольника + 1 замыкающая).
            Рамка может быть незамкнутой
            2) Рамка указанной толщины делится на 4 пересекающихся прямоугольника.
            3) Проверяется, что для каждых соседних точек есть прямоугольник, содержащий эти точки.
            4) Проверяется, что все 4 прямоугольника содержат точки.
            Таким образом проверяется, что точки образуют контур, обходящий рамку, но не выходящий за её пределы.
        """
        if len(line_commands) < 5:
            return False
        first_command = line_commands[0]
        assert isinstance(first_command, MoveTo)
        x0 = first_command.x
        y0 = first_command.y
        fitted_bounds = set()
        for command in line_commands[1:]:
            if not isinstance(command, LineTo):
                return False
            x1 = command.x
            y1 = command.y
            segment_fitted_bounds = self._get_segment_fitted_bounds(x0, y0, x1, y1)
            fitted_bounds.update(segment_fitted_bounds)
            x0 = x1
            y0 = y1
        return len(fitted_bounds) == 4

    def _get_segment_fitted_bounds(self, x0: float, y0: float, x1: float, y1: float) -> Set[int]:
        fitted_bounds = set()
        for index, line_bounds in enumerate(self._frame_line_bounds):
            if line_bounds.contains_point(x0, y0) and line_bounds.contains_point(x1, y1):
                fitted_bounds.add(index)
        return fitted_bounds


def parse_args():
    parser = argparse.ArgumentParser(description='Clean SVG scheme')
    add_source_args(parser)
    parser.add_argument('--out', dest='dir_out', type=str, required=True, help='Output directory')
    return parser.parse_args()


def clean_files(paths: List[str], dir_out: str) -> None:
    cleaner = SvgCleaner()
    for path in paths:
        print(path)
        try:
            cleaner.clean(path, dir_out)
        except KeyboardInterrupt:
            break
        except:
            print(traceback.format_exc())


if __name__ == '__main__':
    args = parse_args()
    source_paths = get_source_paths(args)
    clean_files(source_paths, args.dir_out)
