# Extended Gcode Commands
#
# Copyright (C) 2018  Eric Callahan <arksine.code@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import homing

TMC_REG_COOLCONF = 0x6d

class TRAMZ:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.tmc_z_endstop = None
        self.z_rail = None
        self.enabled = False
        mcu = self.printer.lookup_object('mcu')
        mcu.register_config_callback(self.build_config)
        self._setup_virtual_z_endstop(config)
        self.gcode.register_command(
            "TRAM_Z", self.cmd_TRAM_Z, desc=self.cmd_TRAM_Z_help)
    def build_config(self):
        if self.enabled:
            kin = self.printer.lookup_object('toolhead').get_kinematics()
            self.z_rail = kin.rails[2]
            if self.tmc_z_endstop is not None:
                for stepper in self.z_rail.get_steppers():
                    self.tmc_z_endstop[0].add_stepper(stepper)
    def _setup_virtual_z_endstop(self, config):
        if config.getsection('printer').get('kinematics') != 'cartesian':
            # TRAM_Z only supports cartesian printers
            return
        if config.has_section('stepper_z'):
            z_config = config.getsection('stepper_z')
            endstop = z_config.get('endstop_pin')
            if endstop.startswith("tmc2130"):
                self.enabled = True
            elif config.has_section('tmc2130 stepper_z'):
                self.enabled = True
                ppins = self.printer.lookup_object('pins')
                es = ppins.setup_pin(
                    'endstop', 'tmc2130_stepper_z:virtual_endstop')
                self.tmc_z_endstop = (es, "tmc2130_z_endstop")
    cmd_TRAM_Z_help = "Rams Z-axis to top z-holders, used to align Axis"
    def cmd_TRAM_Z(self, gcmd):
        if not self.enabled:
            gcmd.respond_info("TRAM_Z setup unsuccessful, aborting")
            return
        reactor = self.printer.get_reactor()
        toolhead = self.printer.lookup_object('toolhead')
        idle_timeout = self.printer.lookup_object('idle_timeout')
        event_time = reactor.monotonic()
        status = idle_timeout.get_status(event_time)
        if status['state'] == "Printing":
            gcmd.respond_info("Cannot Tram during a print, aborting")
            return
        if self.tmc_z_endstop is None:
            # TODO: Already Using TMC to home.  Just homing max, home
            # to top, move up 10mm?
            return
        homing_max = self.z_rail.position_max
        gcmd.respond_info("position_min = %f" % self.z_rail.position_min)
        gcmd.respond_info("position_max = %f" % self.z_rail.position_max)
        cur_pos = toolhead.get_position()
        start_pos = list(cur_pos)
        move_pos = list(cur_pos)
        start_pos[2] = self.z_rail.position_min
        move_pos[2] = 220.0
        self.z_rail.position_max = 230.
        toolhead.set_position(start_pos, homing_axes=[2])

        home = homing.HomingMove(self.printer, [self.tmc_z_endstop])
        home.homing_move(move_pos, self.z_rail.homing_speed)
        toolhead.wait_moves()

        # Move up 10mm for tramming
        self.z_rail.position_max = 250.
        next_pos = toolhead.get_position()
        next_pos[2] += 10
        toolhead.move(next_pos, 10.)
        next_pos[2] -= 50
        toolhead.move(next_pos, 20.)
        toolhead.wait_moves()
        self.gcode.run_script_from_command("M84")
        self.z_rail.position_max = homing_max

def load_config(config):
    return TRAMZ(config)
