# @author Martin Pek (martin.pek@web.de)
# Python 3.11

import time
from threading import Thread, Lock
from pyModbusTCP.client import ModbusClient
from time import sleep
import json
from datetime import datetime as dt, timedelta

SERVER_PORT = 502

'''
https://pymodbustcp.readthedocs.io/en/stable/examples/client_thread.html
https://novantaims.com/downloads/manuals/modbus_tcp.pdf
@ TODO: 🔲 ✅

✅ potential need to rework threading to work with pyQT it works but currently the modbus is blocking
🔲 Error 0x0021 2 Variable holds the error code of the last error. 
 must be read or set to 0 to clear.
 — 0

🔲 error handling, logging
🔲 reset error flag after printing, make a function to print and reset errors, this can be later hooked up to logging
✅ make class importable as we need to run this with an UI
✅ read and write process may collide so there needs to be a semaphore of sorts
🔲 register_count is not properly handled
✅ self.last_slew = value for running the writecommand
✅ volumenstrom berechnen
✅ enable makeup mode Make up 0x00A0 to 1

🔲 add exception throw when invalid modbus IP is given
✅ faster startup

ist soll profil mit aktuellem zeitpunk
'''


class ModbusController:

    register_size = 16
    max_register_range = 1 << register_size    # amount of value, the max value is one less since 0 is also a number
    # default of 256, see command 0x0048
    steps_per_rev = 51200

    def __init__(self, ip_address, do_run_preset=False):
        self.__cfg = self.__get_cfg()
        self.__steps_per_liter = self.__cfg.get("steps_per_liter", 0)
        if not self.__steps_per_liter:
            exit("invalid steps to volume conversion in config file")
        # @todo: consider splitting this with zip? command?
        self.__preset_intervals = self.__cfg.get("timeRevIntervals", 0)
        if not self.__preset_intervals:
            exit("invalid interval configuration in config file")
        self.__preset_time_total = timedelta(seconds=sum(sublist[0] for sublist in self.__preset_intervals))

        self.client = ModbusClient(host=ip_address, port=SERVER_PORT, auto_open=True, timeout=0.2)
        self.bus_semaphore = Lock()

        self.stall_occured = False
        self.last_slew = 0
        self.total_steps = 0
        self.step_overflow = 0
        self.total_volume = 0
        self.elapsed_time = timedelta()     # elapsed time till the most recent stop
        self.__start_time = dt.now()        # not technically the start time if start and stops are handled
        self.__stage_time = dt.now()
        self.__stage_elapsed = timedelta()
        self.__preset_stage = -1
        self.__flow_data = []
        self.stage_updated = -1

        self.do_run_preset = do_run_preset
        self.__running = False

        self.__writeActions = {
            "slew": self.WriteCommand(self, 0x0078, (-5000000, +5000000), 2),
            "holdCurrent": self.WriteCommand(self, 0x0029, (0, 100), 1),   # default 5
            "runCurrent": self.WriteCommand(self, 0x0067, (0, 100), 1),    # default 25
            "setTorque": self.WriteCommand(self, 0x00A6, (0, 100), 1),     # default 25
            "setMaxVelocity": self.WriteCommand(self, 0x008B, (+1, 2560000), 2),
            "error": self.WriteCommand(self, 0x0021, (0, 0), 1),
            "driveEnable": self.WriteCommand(self, 0x001C, (0, 1), 1),
            # default is 256 - 51200 steps / rev
            "microStep": self.WriteCommand(self, 0x0048, (1, 256), 1),
            "encodeEnable": self.WriteCommand(self, 0x001E, (0, 1), 1),
            "position": self.WriteCommand(self, 0x0057, (-2147483648, 2147483647), 2),
            "makeUp": self.WriteCommand(self, 0x00A0, (0, 2), 1)
        }

        self.__readAction = {
            "stalled": self.ReadCommand(self, 0x007B),
            "moving": self.ReadCommand(self, 0x004A),
            "outputFault": self.ReadCommand(self, 0x004E),
            "error": self.ReadCommand(self, 0x0021),
            # If hybrid circuitry is in make-up mode, 0x0085-86 will not return an accurate value.
            # When the hybrid product is in torque control mode 0x0085-86 will return a zero (0).
            "velocity": self.ReadCommand(self, 0x0085, 2),
            "position": self.ReadCommand(self, 0x0057, 2)
        }

        self.__writeActions["encodeEnable"].set_value(1)
        self.__writeActions['error'].set_value(0)
        self.__writeActions['position'].set_value(0)
        self.__writeActions['makeUp'].set_value(1)
        self.set_run_current(100)
        self.halt()

        self.polling_thread = None

        if self.do_run_preset:
            self.__run_preset()

    def convert_value_to_register(self, value, value_range, register_count):
        clipped_value = max(min(value, value_range[1]), value_range[0])
        if clipped_value != value:
            print(f"Value: {value} was out of range {value_range}. Clipped to {clipped_value}")
            value = clipped_value
        abs_range = sum(abs(x) for x in value_range)
        # checking if it's a single register write, if so we can already skip all conversion
        if abs_range < self.max_register_range:
            return [value]
        else:
            high_register = (value >> self.register_size) & 0xFFFF
            low_register = value & 0xFFFF
            return [low_register, high_register]

    class ReadCommand:
        def __init__(self, modbus, register, register_count=1):
            self.register = register
            self.register_count = register_count
            self.modbus = modbus

        def get_regs(self):
            self.modbus.bus_semaphore.acquire()
            regs_l = self.modbus.client.read_holding_registers(self.register, self.register_count)
            self.modbus.bus_semaphore.release()

            if regs_l is None:
                print("communication error, no value returned\n")
                return False

            if len(regs_l) > 2:
                print("unexpected return length")
                return False
            if len(regs_l) == 2:
                low_register, high_register = regs_l
                combined_value = (high_register << 16) | low_register
                if combined_value & (1 << 31):
                    combined_value -= (1 << 32)
                regs_l = [combined_value]

            return regs_l[0]

    class WriteCommand:
        def __init__(self, modbus, register, value_range, register_count):
            self.modbus = modbus
            self.register = register
            self.value_range = value_range
            self.register_count = register_count

        def set_value(self, value):
            register_value = self.modbus.convert_value_to_register(value, self.value_range, self.register_count)
            self.modbus.bus_semaphore.acquire()
            res = self.modbus.client.write_multiple_registers(self.register, register_value)
            self.modbus.bus_semaphore.release()
            if res or not (self.modbus.client.last_error and self.modbus.client.last_except):
                return True

            # does this reset automatically with the next command? no manual function for that listed afaik
            print(self.modbus.client.last_error_as_txt)
            print(self.modbus.client.last_except_as_full_txt)

            return False

    def set_run_current(self, value):
        self.__writeActions["runCurrent"].set_value(value)

    def set_slew(self, value):
        self.__writeActions["slew"].set_value(value)
        self.last_slew = value

    def set_slew_revs_minute(self, revs):
        value = round((revs / 60) * self.steps_per_rev)
        self.set_slew(value)

    @staticmethod
    def __get_cfg():
        try:
            with open('config.json', 'r') as config_file:
                return json.load(config_file)
        except FileNotFoundError:
            print("missing config file")
        except json.decoder.JSONDecodeError as err:
            print(f"Config error:\n{err} \ncannot open config")
        exit()

    # might be deprecated if run purely via UI
    def __run_preset(self):
        # wild guess we are working with non programmers or matlab "people" (such an evil word)
        start_index = self.__cfg.get("startAt", 1) - 1
        intervals = self.__cfg.get("timeRevIntervals")

        for interval in intervals[start_index:]:
            try:
                self.set_slew_revs_minute(interval[1])
                sleep(interval[0])
            except KeyboardInterrupt:
                return

    def __update_preset_stage(self, set_slew=False):

        if set_slew:
            self.__stage_time = dt.now()

        if self.__preset_stage >= len(self.__preset_intervals):
            return

        # second line here needs to take something like
        if self.__preset_stage < 0 or \
                self.__get_stage_elapsed() > timedelta(seconds=self.__preset_intervals[self.__preset_stage][0]):
            self.__preset_stage += 1
            self.__stage_time = dt.now()
            self.__stage_elapsed = timedelta()
            print(f"\n\n\npreset stage is {self.__preset_stage}")
            if len(self.__preset_intervals) <= self.__preset_stage:
                self.stop()
                return
            self.stage_updated = self.__preset_stage
            set_slew = True

        if set_slew:
            self.set_slew_revs_minute(self.__preset_intervals[self.__preset_stage][1])

    def is_running(self):
        return self.__running

    def start(self):
        if self.polling_thread is None:
            self.polling_thread = Thread(target=self.polling_fnc)
            # set daemon: polling thread will exit if main thread exit
            self.polling_thread.daemon = True
            self.polling_thread.start()

        self.__start_time = dt.now()
        self.__running = True
        self.__update_preset_stage(True)

    def stop(self):
        self.elapsed_time = self.get_elapsed_time()
        self.__stage_elapsed = self.__get_stage_elapsed()
        self.__running = False
        self.halt()

    def get_elapsed_time(self):
        if self.__running:
            return self.elapsed_time + (dt.now() - self.__start_time)
        else:
            return self.elapsed_time

    def __get_stage_elapsed(self):
        return self.__stage_elapsed + (dt.now() - self.__stage_time)

    def get_progress_percentage(self):
        return int((self.get_elapsed_time().seconds/self.__preset_time_total.seconds) * 100)

    def pop_flowrate_data(self):
        data = self.__flow_data
        self.__flow_data = []
        return data

    def halt(self):
        self.set_slew(0)

    def get_preset_list(self):
        return self.__preset_intervals

    def override_stage(self, index):
        self.__preset_stage = index
        if self.__running:
            self.__update_preset_stage(True)

    def polling_fnc(self):

        while True:
            if not self.__running:
                continue

            self.__update_preset_stage()

            moving = self.__readAction['moving'].get_regs()
            print(f"moving: {moving}")
            if not moving and self.last_slew:
                self.stall_occured = True
                '''
                right here an error is thrown but without consequences as much as i can tell, delays don't fix this
                modbus exception
                Unrecoverable error occurred while slave was attempting to perform requested action.
                '''
                self.__writeActions["slew"].set_value(self.last_slew)
            position = self.__readAction['position'].get_regs()
            print(f"position: {position}")
            # an overflow hitting 32 uint limit is 41943,04 revolutions with the default resolution
            self.total_steps = self.step_overflow + position
            self.total_volume = self.total_steps / self.__steps_per_liter
            if abs(position) > 1 << 30:
                self.step_overflow += position
                self.__writeActions['position'].set_value(0)
            print(f"total volume: {self.total_volume} L / total steps: {self.total_steps}")
            velocity = self.__readAction['velocity'].get_regs()
            print(f"velocity: {velocity} steps/s")
            print(f"flowrate: {60 * velocity / self.__steps_per_liter} L/min")

            self.__flow_data.append([self.get_elapsed_time().total_seconds(), self.total_volume])

            err = self.__readAction['error'].get_regs()
            if err:
                print(f"error: {err}")
                self.__writeActions['error'].set_value(0)
                output_fault = self.__readAction['outputFault'].get_regs()
                if output_fault:
                    print(f"outputFault: {output_fault}")

            time.sleep(0.1)


def main():
    run_preset = False
    modbus_controller = ModbusController('192.168.59.35', run_preset)
    # modbus_controller.__readAction["error"].get_regs()

    if not run_preset:
        try:
            modbus_controller.set_slew_revs_minute(20)
            sleep(20)
        except KeyboardInterrupt:
            modbus_controller.set_slew(0)

    modbus_controller.set_slew(0)


if __name__ == "__main__":
    main()
