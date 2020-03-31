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


import os
import re
import logging
import subprocess


class LFSOstItem:

    def __init__(self, target, ost, state, active):

        self.target = target
        self.ost = ost
        self.state = state
        self.active = active


class LFSUtils:

    def __init__(self, lfs_bin):

        self.lfs_bin = lfs_bin
        self.ost_prefix_len = len('OST')
        self.ost_active_output = ' active.'

        if not os.path.isfile(self.lfs_bin):
            raise RuntimeError("LFS binary was not found under: '%s'" % self.lfs_bin)

    def create_ost_item_list(self, target):

        ost_list = list()

        try:

            regex_str = target + "\-(OST[a-z0-9]+)\-[a-z0-9-]+\s(.+)"
            logging.debug("Using OST regex: %s" % regex_str)
            pattern = re.compile(regex_str)

            args = ['sudo', self.lfs_bin, 'check', 'osts']

            # TODO: Python3.5
            # process_result = subprocess.run(args,
            #                                 check=True,
            #                                 stdout=subprocess.PIPE,
            #                                 stderr=subprocess.PIPE)

            output = subprocess.check_output(args, stderr=subprocess.STDOUT).decode('UTF-8')

            for line in output.strip().split('\n'):

                match = pattern.match(line.strip())

                if match:

                    ost = match.group(1)
                    state = match.group(2)

                    if state == "active.":
                        ost_list.append(LFSOstItem(target, ost, state, True))
                    else:
                        ost_list.append(LFSOstItem(target, ost, state, False))

                else:
                    logging.warning("No regex match for line: %s" % line)

        except Exception as e:
            logging.error("Exception occurred: %s" % e)

        return ost_list

    def is_ost_active(self, target, ost):

        for ost_item in self.create_ost_item_list(target):

            if ost_item.ost == ost:

                if ost_item.active:
                    return True
                else:
                    return False

        raise RuntimeError("[LFSUtils::is_ost_active] OST not found: %s" % ost)

    def set_stripe(self, ost_idx, file_path):
        """Throws subprocess.CalledProcessError on error in subprocess.check_output"""

        logging.debug("Setting stripe settings for file: %s on OST: %s" % (file_path, ost_idx))

        args = [self.lfs_bin, 'setstripe', '-i', ost_idx, file_path]

        # TODO Use subprocess.run() with Python3.5
        subprocess.check_output(args, stderr=subprocess.STDOUT).decode('UTF-8')
