#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2020 Gabriele Iannetti <g.iannetti@gsi.de>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


import subprocess
import logging
import signal
import time
import os

from multiprocessing import Process
from ctrl.critical_section import CriticalSection
from ctrl.ost_info import OSTInfo
from lfs.lfs_utils import LFSUtils


class OSTListProcessor(Process):

    def __init__(self,
                 ost_info_queue,
                 lock_ost_queue,
                 config_file_reader,
                 local_mode=False):

        super(OSTListProcessor, self).__init__()

        self.measure_interval = config_file_reader.measure_interval
        self.lfs_bin = config_file_reader.lfs_bin
        self.lfs_target = config_file_reader.lfs_target
        self.ost_select_list = config_file_reader.ost_select_list

        self.ost_info_queue = ost_info_queue
        self.lock_ost_queue = lock_ost_queue

        self.local_mode = local_mode

        self.run_flag = False

        self.lfs_utils = LFSUtils(self.lfs_bin)

    def start(self):
        super(OSTListProcessor, self).start()

    def run(self):

        self.run_flag = True

        signal.signal(signal.SIGTERM, self._signal_handler_terminate)
        signal.siginterrupt(signal.SIGTERM, True)

        while self.run_flag:

            try:

                logging.debug("OSTListProcessor active!")

                ost_info_list = None

                if self.local_mode:
                    ost_info_list = self._create_local_ost_info_list()
                else:
                    ost_info_list = self._create_ost_info_list()

                logging.debug("Length of OST info list: %s" % len(ost_info_list))

                with CriticalSection(self.lock_ost_queue):

                    if not self.ost_info_queue.is_empty():
                        self.ost_info_queue.clear()

                    if ost_info_list:
                        self.ost_info_queue.fill(ost_info_list)

                time.sleep(self.measure_interval)

            except InterruptedError as e:
                logging.debug("Caught InterruptedError exception.")

            except Exception as e:
                logging.error("Caught exception in OSTListProcessor: %s" % e)
                os._exit(1)

        logging.debug("OSTListProcessor finished!")
        os._exit(0)

    def _signal_handler_terminate(self, signum, frame):

        self.run_flag = False

        msg = "OSTListProcessor retrieved signal to terminate."
        logging.debug(msg)
        raise InterruptedError(msg)

    def _create_ost_info_list(self):

        ost_info_list = list()

        ost_item_list = self.lfs_utils.create_ost_item_list(self.lfs_target)

        for ost_item in ost_item_list:
            ost_info_list.append(OSTInfo(ost_item.name))

        if len(ost_info_list) == 0:
            raise RuntimeError("OST list is empty!")

        if len(self.ost_select_list):

            select_ost_info_list = list()

            for select_ost_name in self.ost_select_list:

                found_select_ost_name = False

                for ost_info in ost_info_list:

                    if select_ost_name == ost_info.ost_name:

                        select_ost_info_list.append(ost_info)

                        found_select_ost_name = True

                        logging.debug("Found OST from selected list: %s" % select_ost_name)

                        break

                if found_select_ost_name is False:
                    raise RuntimeError("OST to select was not found in ost_info_list: %s" % select_ost_name)

            if not len(select_ost_info_list):
                raise RuntimeError("Select OST info list is not allowed to be empty when selecting OSTs!")

            return select_ost_info_list

        else:
            return ost_info_list

    def _create_local_ost_info_list(self):

        ost_info_list = list()

        max_ost_idx = 100

        for ost_idx in range(max_ost_idx):
            ost_info_list.append(OSTInfo(str(ost_idx)))

        if len(self.ost_select_list):

            select_ost_info_list = list()

            for select_ost_name in self.ost_select_list:

                found_select_ost_name = False

                for ost_info in ost_info_list:

                    if select_ost_name == ost_info.ost_name:

                        logging.debug("Found OST from selected list: %s" %
                                      select_ost_name)

                        if not found_select_ost_name:
                            found_select_ost_name = True

                        select_ost_info_list.append(ost_info)

                        break

                if not found_select_ost_name:
                    raise RuntimeError("OST to select was not found "
                                       "in ost_info_list: %s" % select_ost_name)

            return select_ost_info_list

        else:
            return ost_info_list

