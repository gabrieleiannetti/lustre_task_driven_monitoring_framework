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


import inspect

from base_message import BaseMessage
from message_type import MessageType
from task.base_task import BaseTask
from task.task_factory import TaskFactory


class TaskAssign(BaseMessage):
    """The Master sends this message to a controller to assign a task."""

    """
        The __init__ method can take two different types of arguments:
        
        1. A task object - if the master sends this message to a controller.
        2. A string object - if the controller retrieves this message from the master.
    """
    def __init__(self, value):

        header = None
        body = None

        if not value:
            raise RuntimeError("No value has been passed!")

        if type(value) == str:

            message_items = value.split(BaseMessage.field_separator)
            count_message_items = len(message_items)
            len_message = len(value)

            if count_message_items < 5:
                raise RuntimeError("Invalid header size found in message: '%s'" % value)

            header = message_items[0] \
                + BaseMessage.field_separator \
                + message_items[1] \
                + BaseMessage.field_separator \
                + message_items[2] \
                + BaseMessage.field_separator \
                + message_items[3] \
                + BaseMessage.field_separator \
                + message_items[4]

            len_header = len(header)

            if len_header < len_message:
                body = value[len_header + 1:len_message]

        else:

            task_class = value.__class__
            task_base_classes = task_class.__bases__

            if (len(task_base_classes) != 1) or (task_base_classes[0].__name__ != BaseTask.__name__):
                raise RuntimeError("The following task is just allowed to inherit from BaseTask class: '%s'"
                                   % task_class)

            header = TaskAssign._create_header(value, task_class)
            body = TaskAssign._create_body(value, task_class)

        super(TaskAssign, self).__init__(header, body)

    @staticmethod
    def _create_header(task, task_class):

        if not ("task." in task_class.__module__):
            raise RuntimeError("A task has to be located into the 'task' package!")

        if not task.ost_name or task.ost_name == '':
            raise RuntimeError("Initialization of the attribute 'ost_name' is missing for task: '%s'" % task_class)

        if not task.oss_ip or task.oss_ip == '':
            raise RuntimeError("Initialization of the attribute 'oss_ip' is missing for task: '%s'" % task_class)

        header = MessageType.TASK_ASSIGN() \
            + BaseMessage.field_separator \
            + task_class.__module__ \
            + BaseMessage.field_separator \
            + task_class.__name__ \
            + BaseMessage.field_separator \
            + task.ost_name \
            + BaseMessage.field_separator \
            + task.oss_ip

        return header

    @staticmethod
    def _create_body(task, task_class):

        # Build body
        args_list = inspect.getargspec(task_class.__init__).args
        len_args_list = len(args_list)

        # Skip first parameter 'self' of the __init__ method which is a convention in Python for that method.
        if len_args_list == 2:
            body = str(getattr(task, args_list[1]))

        if len_args_list > 2:

            body = str(getattr(task, args_list[1]))

            # Ordering of the arguments from the __init__ method is relevant!
            # getattr throws an exception if an argument is not found in the task object.
            for index in range(2, len(args_list)):
                body += BaseMessage.field_separator + str(getattr(task, args_list[index]))

        return body

    def to_task(self):
        return TaskFactory.create_from_message(BaseMessage(self.header, self.body))

