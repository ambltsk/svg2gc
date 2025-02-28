#!./venv/bin/python

import os
import sys
import argparse

from svgpathtools import Document, wsvg, \
        Path, Line, QuadraticBezier, CubicBezier, Arc

from config import load_config, PostProcessor

config = None
x_doc_min, y_doc_min, x_doc_max, y_doc_max = 0, 0, 0, 0

SVG_NS = '{http://www.inkscape.org/namespaces/inkscape}'

def get_paths(doc, name_layer):
    """
    Получеие путей по имени метки слоя

    name_layer: метка слоя (label, не id!)
    """
    group = doc.get_group([name_layer], name_attr = f'{SVG_NS}label')
    if group is not None:
        paths = doc.paths_from_group([group.attrib.get('id', '')])
        return group, paths
    return group, None

def curve_approximation(curve, segm_len=1):
    """
    Апроксимация кривой в ряд коротких прямых лини

    curve: кривая
    segm_len: длина одного сегмента
    """
    num_points = int(curve.length() / segm_len)
    if num_points == 0:
        return
    points = []
    lines = []
    for p in range(num_points+1):
        points.append(curve.point(p/num_points))
        if p > 0:
            lines.append(Line(points[p-1], points[p]))
    return Path(*lines)

def contour_processing(contour):
    """
    Обработка контура - конвертация его в ряд прямых линий

    contour: список путей Path
    """
    paths = []
    for path in contour:
        for segment in path:
            if isinstance(segment, (CubicBezier, QuadraticBezier, Arc)):
                paths.append(curve_approximation(segment))
            else:
                paths.append(segment)
    return paths

def engrave_fill(contour, beam_width = 1):

    xmin, xmax, ymin, ymax = contour.bbox()

    paths = []

    num_line = int((xmax - xmin) / beam_width) + 1

    for x in range(num_line):
        cur_x = xmin + x * beam_width
        section = Line(complex(cur_x, ymin), complex(cur_x, ymax))
        intersection = contour.intersect(section)
        if intersection and len(intersection) > 1:
            y_intersection_points = [l.point(p).imag for p, l, _  in [i[1] for i in intersection]]
            if x % 2 == 0:
                y_intersection_points.sort()
            else:
                y_intersection_points.sort(reverse=True)
            for i, y in enumerate(y_intersection_points[1:]):
                ymid = y_intersection_points[i] + (y - y_intersection_points[i]) / 2
                ray = Line(complex(cur_x, ymid), complex(xmax, ymid))
                count_intersection_ray = len(contour.intersect(ray))
                if count_intersection_ray % 2 != 0:
                    line = Line(complex(cur_x, y_intersection_points[i]), complex(cur_x, y))
                    paths.append(line)
    return paths

def extract_segments(paths, segments = []):
    for path in paths:
        if isinstance(path, Path):
            segments.extend(extract_segments(path, []))
        elif path is None:
            continue
        else:
            segments.append(path)
    return segments

def processing_path(paths, parametr, lastx, lasty, lasts):

    def r(i, axis):
        if config.START_COORD == 'sw':
            if axis == 'Y':
                return round(y_doc_max - i, config.ACCURACY)
            else:
                return round(i, config.ACCURACY)
        elif config.START_COORD == 'se':
            if axis == 'Y':
                return round(y_doc_max - i, config.ACCURACY)
            else:
                return round(x_doc_max - i, config.ACCURACY)
        elif config.START_COORD == 'ne':
            if axis == 'Y':
                return round(i, config.ACCURACY)
            else:
                return round(x_doc_max - i, config.ACCURACY)
        elif config.START_COORD == 'c':
            if axis == 'Y':
                return round(i - y_doc_max / 2, config.ACCURACY)
            else:
                return round(i - x_doc_max / 2, config.ACCURACY)
        else:
            return round(i, config.ACCURACY)

    process = []

    first_path = paths[0]
    # Передвежение до первой точки
    xs = first_path.start.real
    ys = first_path.start.imag
    if lastx != xs or lasty != ys:
        process.append({'action': 'off', 'power': 'move'})
        process.append({'action': 'move',
                        'X': r(float(xs), 'X') if xs != lastx else None,
                        'Y': r(float(ys), 'Y') if ys != lasty else None,
                        'speed': 'travel' if lasts != 'travel' else None})
        lasts = 'travel'
    process.append({'action': 'on', 'power': parametr})
    for i, path in enumerate(paths):
        # Жгем линию
        xe = path.end.real
        ye = path.end.imag
        process.append({'action':'line',
                        'speed': parametr if lasts != parametr else None,
                        'X': r(float(xe), 'X') if xe != xs else None,
                        'Y': r(float(ye), 'Y') if ye != ys else None})
        lasts = parametr
        if i < len(paths) - 1:               # Если это не последний путь
            if path.end != paths[i+1].start: # Начало следующего пути не равно концу текущего - перемещаемся
                xs = paths[i+1].start.real
                ys = paths[i+1].start.imag
                process.append({'action': 'off', 'power': 'move'})
                process.append({'action': 'move',
                                'X': r(float(xs), 'X') if xs != xe else None,
                                'Y': r(float(ys), 'Y') if ys != ye else None,
                                'speed': 'travel' if lasts != 'travel' else None})
                process.append({'action': 'on', 'power': parametr})
            else:
                xs, ys = xe, ye

    return process, xe, ye, lasts

def processing_file(pfe, pce, pe, pci, pco):
    process = []
    lastx = 0
    lasty = 0
    lasts = ''
    if len(pfe) > 0:
        process.append({'action': 'comment', 'text': 'start engrave fill strategy'})
        portion, lastx, lasty, lasts = processing_path(pfe,
                                                'engrave_fill',
                                                lastx, lasty, lasts)
        process.extend(portion)
        process.append({'action': 'comment', 'text': 'finish engrave fill strategy'})
    if len(pce) > 0:
        process.append({'action': 'comment', 'text': 'start engrave contour strategy'})
        portion, lastx, lasty, lasts = processing_path(pce,
                                                'engrave_contour',
                                                lastx, lasty, lasts)
        process.extend(portion)
        process.append({'action': 'comment', 'text': 'finish engrave contour strategy'})
    if len(pe) > 0:
        process.append({'action': 'comment', 'text': 'start engrave strategy'})
        portion, lastx, lasty, lasts = processing_path(pe,
                                                'engrave',
                                                lastx, lasty, lasts)
        process.extend(portion)
        process.append({'action': 'comment', 'text': 'finish engrave strategy'})
    if len(pci) > 0:
        process.append({'action': 'comment', 'text': 'start cut in strategy'})
        for p in range(config.CUT_PASSES):
            process.append({'action': 'comment', 'text': f'pass {p+1}'})
            portion, lastx, lasty, lasts = processing_path(pci,
                                                'cut',
                                                lastx, lasty, lasts)
            process.extend(portion)
        process.append({'action': 'comment', 'text': 'finish cut in strategy'})
    if len(pco) > 0:
        process.append({'action': 'comment', 'text': 'start cut out strategy'})
        for p in range(config.CUT_PASSES):
            process.append({'action': 'comment', 'text': f'pass {p+1}'})
            portion, lastx, lasty, lasts = processing_path(pco,
                                                'cut',
                                                lastx, lasty, lasts)
            process.extend(portion)
        process.append({'action': 'comment', 'text': 'finish cut out strategy'})
    return process

def postprocess(process):

    pass

def main(doc, file_out, pp_rule):

    engrave_fill_g, engrave_fill_paths = get_paths(doc, config.ENGRAVE_FILL_LAYER)
    engrave_g, engrave_paths = get_paths(doc, config.ENGRAVE_LAYER)
    cut_in_g, cut_in_paths = get_paths(doc, config.CUT_IN_LAYER)
    cut_out_g, cut_out_paths = get_paths(doc, config.CUT_OUT_LAYER)

    paths_contour_ef = extract_segments((engrave_fill_paths), [])
    paths_fill_ef = []
    if engrave_fill_paths is not None:
        for path in engrave_fill_paths:
            paths_fill_ef.extend(engrave_fill(path, beam_width = config.BEAM_THICKNESS))
    paths_e = extract_segments(contour_processing(engrave_paths), [])
    paths_ci = extract_segments(contour_processing(cut_in_paths), [])
    paths_co = extract_segments(contour_processing(cut_out_paths), [])

    process = processing_file(paths_fill_ef,
                          paths_contour_ef,
                          paths_e,
                          paths_ci,
                          paths_co)

    pp = PostProcessor(process, pp_rule, config)
    pp.save_gcode(file_out)

def create_parser():
    parser = argparse.ArgumentParser(prog='svg2marlin.py',
                    description='Преобразует пути в файле SVG в GCODE для лазерной резки',
                    epilog='Больще информации на https://amb-club.ru')
    parser.add_argument('svgfile')
    parser.add_argument ('-c', '--config', default='svg2gc.conf',
                                    help='Файл конфигурации')
    parser.add_argument ('-o', '--output', default='out.gcode',
                                    help='Итоговый файл GCODE')
    parser.add_argument ('-p', '--postprocess', default=None,
                                    help='Постпроцессор для формирования файла GCODE')

    return parser

if __name__ == '__main__':

    parser = create_parser()
    namespace = parser.parse_args(sys.argv[1:])

    file_in = namespace.svgfile

    if not os.path.exists(file_in):
        print('Ошибка: Файл svg не найден')
        sys.exit(1)

    config = load_config(namespace.config)

    doc = Document(file_in)
    x_doc_min, y_doc_min, x_doc_max, y_doc_max =  [float(i) for i in doc.root.attrib.get('viewBox').split()]

    main(doc, namespace.output, namespace.postprocess or config.POST_PROCESS)

