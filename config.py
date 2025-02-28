import os
import re
from dataclasses import dataclass


@dataclass
class Config():

    CUT_PASSES = 2
    CUT_SPEED = 120
    ENGRAVE_FILL_SPEED = 700
    ENGRAVE_CONTOUR_SPEED = 700
    ENGRAVE_SPEED = 700
    FREE_TRAVEL_SPEED = 2000

    POWER_CUT = 245
    POWER_ENGRAVE = 75
    POWER_ENGRAVE_CONTOUR = 75
    POWER_ENGRAVE_FILL = 75
    POWER_MOVE = 1

    ACCURACY = 3

    BEAM_THICKNESS = 0.5

    ENGRAVE_FILL_LAYER = 'ef'
    ENGRAVE_LAYER = 'e'
    CUT_IN_LAYER = 'ci'
    CUT_OUT_LAYER = 'co'

    START_COORD = 'sw'

    POST_PROCESS = 'marlin'
    POST_PROCESS_DIR = 'pp'

CONFIG_FILE = 'svg2gc.conf'

def load_config(filename = CONFIG_FILE):
    config = Config()
    if not os.path.exists(filename):
        return config
    with open(filename, 'r') as config_file:
        config_data = config_file.read()
    for line in re.split(r'[\n\r]', config_data):
        if line.strip().startswith('#') or not line:
            continue
        params = re.split(r'\s*=\s*', line)
        if len(params) < 2:
            continue
        try:
            attr = getattr(config, params[0].upper())
        except:
            continue
        if re.match(r'^\d+$', params[1].strip()):
            setattr(config, params[0].upper(), int(params[1]))
        elif re.match(r'^\d*\.\d+', params[1].strip()):
            setattr(config, params[0].upper(), float(params[1]))
        else:
            setattr(config, params[0].upper(), params[1])

    return config

class PostProcessor():

    def __init__(self, process: list, rule: str, config: Config):

        self.process = process
        self.rule = rule
        self.config = config

        self.start_gcode = ''
        self.end_gcode = ''

        self.move_command = ''
        self.move_X = ''
        self.move_Y = ''
        self.move_speed = ''

        self.line_command = ''
        self.line_X = ''
        self.line_Y = ''
        self.line_speed = ''

        self.on_command = ''
        self.on_power = ''

        self.off_command = ''
        self.off_power = ''

        self.comment_text = ''

        self._rule_parser()

    def _rule_parser(self):
        base_dir = os.path.split(__file__)[0]
        ppr_dir = self.config.POST_PROCESS_DIR
        rule_file = os.path.join(base_dir, ppr_dir, f'{self.rule}.ppr')
        if not os.path.exists(rule_file):
            return
        raw = open(rule_file, 'r').read()

        for param in re.findall(r'\[[\S\s]*?\*\}', raw):
            split = re.match(r'\[(.+)\]\s\{\*([\s\S]+)\*\}', param)
            if split:
                attr = split.group(1).replace(' ','_')
                if attr == 'start_gcode':
                    self.start_gcode = split.group(2) + '\n'
                elif attr == 'end_gcode':
                    self.end_gcode = split.group(2)
                else:
                    self._param_parser(attr, split.group(2))

    def _param_parser(self, action, data):
        params = [p for p in re.split(r'[\n\r]', data) if p]
        for param in params:
            split = param.split(':')
            if len(split) > 1 and hasattr(self, f'{action}_{split[0]}'):
                setattr(self, f'{action}_{split[0]}',
                    split[1].strip().replace('_',' '))

    def create_gcode(self):
        gcode = self.start_gcode

        for command in self.process:
            if command.get('action') and \
                    hasattr(self, f'_process_{command["action"]}') and \
                    callable(getattr(self, f'_process_{command["action"]}')):
                gcode += getattr(self, f'_process_{command["action"]}')(command)

        gcode += self.end_gcode

        return gcode

    def _process_line(self, command):
        line = self.line_command
        if command.get('X'):
            line += self.line_X.format(x = command['X'])
        if command.get('Y'):
            line += self.line_Y.format(y = command['Y'])
        if command.get('speed'):
            line += self.line_speed.format(speed = self._get_speed(command['speed']))
        return line + '\n'

    def _process_move(self, command):
        line = self.move_command
        if command.get('X'):
            line += self.move_X.format(x = command['X'])
        if command.get('Y'):
            line += self.move_Y.format(y = command['Y'])
        if command.get('speed'):
            line += self.move_speed.format(speed = self._get_speed(command['speed']))
        return line + '\n'

    def _process_on(self, command):
        line = self.off_command
        if command.get('power'):
            line += self.off_power.format(power = self._get_power(command['power']))
        return line + '\n'

    def _process_off(self, command):
        line = self.off_command
        if command.get('power'):
            line += self.off_power.format(power = self._get_power(command['power']))
        return line + '\n'

    def _process_comment(self, command):
        return self.comment_text.format(text=command.get('text')) + '\n'

    def _get_power(self, power):
        if power == 'move':
            return self.config.POWER_MOVE
        elif power == 'engrave_fill':
            return self.config.POWER_ENGRAVE_FILL
        elif power == 'engrave_contour':
            return self.config.POWER_ENGRAVE_CONTOUR
        elif power == 'engrave':
            return self.config.POWER_ENGRAVE
        elif power == 'cut':
            return self.config.POWER_CUT
        else:
            return 0

    def _get_speed(self, speed):
        if speed == 'move':
            return self.config.FREE_TRAVEL_SPEED
        elif speed == 'engrave_fill':
            return self.config.ENGRAVE_FILL_SPEED
        elif speed == 'engrave_contour':
            return self.config.ENGRAVE_CONTOUR_SPEED
        elif speed == 'engrave':
            return self.config.ENGRAVE_SPEED
        elif speed == 'cut':
            return self.config.CUT_SPEED
        else:
            return 1000

    def save_gcode(self, filename):
        gcode = self.create_gcode()
        open(filename, 'w').write(gcode)

if __name__ == '__main__':

    process = [{'action': 'comment', 'text': 'finish cut in strategy'},
 {'action': 'comment', 'text': 'start cut out strategy'},
 {'action': 'comment', 'text': 'pass 1'},
 {'action': 'off', 'power': 'move'},
 {'X': 33.124, 'Y': 0.934, 'action': 'move', 'speed': 'travel'},
 {'action': 'on', 'power': 'cut'},
 {'X': 8.539, 'Y': 0.255, 'action': 'line', 'speed': 'cut'},
 {'X': 0.296, 'Y': 23.426, 'action': 'line', 'speed': None},
 {'X': 19.787, 'Y': 38.426, 'action': 'line', 'speed': None},
 {'X': 40.075, 'Y': 24.525, 'action': 'line', 'speed': None},
 {'X': 33.124, 'Y': 0.934, 'action': 'line', 'speed': None},
 {'action': 'comment', 'text': 'pass 2'},
 {'action': 'on', 'power': 'cut'},
 {'X': 8.539, 'Y': 0.255, 'action': 'line', 'speed': None},
 {'X': 0.296, 'Y': 23.426, 'action': 'line', 'speed': None},
 {'X': 19.787, 'Y': 38.426, 'action': 'line', 'speed': None},
 {'X': 40.075, 'Y': 24.525, 'action': 'line', 'speed': None},
 {'X': 33.124, 'Y': 0.934, 'action': 'line', 'speed': None},
 {'action': 'comment', 'text': 'finish cut out strategy'}]

    post = PostProcessor(process, 'marlin', Config())
    print(post.create_gcode())

