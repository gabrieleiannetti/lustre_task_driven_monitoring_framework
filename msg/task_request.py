#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2017 Gabriele Iannetti <g.iannetti@gsi.de>
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


from base_message import BaseMessage
from message_type import MessageType


class TaskRequest(BaseMessage):

    def __init__(self, sender):

        if not sender:
            raise RuntimeError('No sender is set!')

        BaseMessage.__init__(self, MessageType.TASK_REQUEST(), sender)

    def validate_body(self):

        if not self.body:
            raise RuntimeError('No body is set!')

    @property
    def sender(self):
        return self.body