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


import argparse
import logging
import multiprocessing
import os
import signal
import sys
import time

from worker import Worker
from worker import WorkerState
from worker import WorkerStateTableItem
from comm.controller_handler import ControllerCommHandler
from conf.controller_config_file_reader import ControllerConfigFileReader
from ctrl.pid_control import PIDControl
from ctrl.critical_section import CriticalSection
from ctrl.shared_queue import SharedQueue
from msg.message_factory import MessageFactory
from msg.message_type import MessageType
from msg.task_finished import TaskFinished
from msg.task_request import TaskRequest
from msg.heartbeat import Heartbeat
from task.poisen_pill import PoisenPill


VERSION = "1.5.0"
RUN_CONDITION = True


def init_arg_parser():

    parser = argparse.ArgumentParser(description='LFSM Controller')

    default_config_file = "/etc/lfsm/controller.conf"

    parser.add_argument('-f',
                        '--config-file',
                        dest='config_file',
                        type=str,
                        required=False,
                        help=str('Path to the config file (default: %s)'
                                 % default_config_file),
                        default=default_config_file)

    parser.add_argument('-D',
                        '--debug',
                        dest='enable_debug',
                        required=False,
                        action='store_true',
                        help='Enables debug log messages.')

    parser.add_argument('-v',
                        '--version',
                        dest='print_version',
                        required=False,
                        action='store_true',
                        help='Print version number')

    return parser.parse_args()


def init_logging(log_filename, enable_debug):

    if enable_debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    if log_filename:
        logging.basicConfig(filename=log_filename, level=log_level, format="%(asctime)s - %(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=log_level, format="%(asctime)s - %(levelname)s: %(message)s")


def create_worker_ids(worker_count):

    worker_ids = list()

    for i in range(0, worker_count):
        worker_ids.append("WORKER_" + str(i))

    return worker_ids


def create_worker_state_table(worker_ids):

    worker_state_table = dict()

    for i in range(0, len(worker_ids)):
        worker_state_table[worker_ids[i]] = WorkerStateTableItem()

    if len(worker_state_table) != len(worker_ids):
        raise RuntimeError("Inconsistent worker state table size found: %s - expected: %s"
                           % (len(worker_state_table), len(worker_ids)))

    return worker_state_table


def create_worker(worker_state_table,
                  lock_worker_state_table,
                  task_queue,
                  result_queue,
                  cond_result_queue):

    worker_handle_dict = dict()

    for worker_id in worker_state_table.keys():

        worker_state_table_item = worker_state_table[worker_id]

        worker_handle = \
            Worker(worker_id,
                   worker_state_table_item,
                   lock_worker_state_table,
                   task_queue,
                   result_queue,
                   cond_result_queue)

        worker_handle_dict[worker_id] = worker_handle

    return worker_handle_dict


def start_worker(worker_handle_dict, worker_state_table):

    if not len(worker_handle_dict):
        raise RuntimeError("Empty worker handle dict!")

    if len(worker_handle_dict) != len(worker_state_table):
        raise RuntimeError('Different sizes in worker handle dict and worker state table detected!')

    for worker_id in worker_handle_dict.keys():
        worker_handle_dict[worker_id].start()

    max_retry_count = 3
    for retry_count in range(1, max_retry_count + 1):

        worker_ready = True

        for worker_id in worker_handle_dict.keys():

            if not (worker_handle_dict[worker_id].is_alive()
                    and worker_state_table[worker_id].get_state == WorkerState.READY):
                worker_ready = False

        if worker_ready:
            return True

        time.sleep(retry_count * retry_count)
        logging.debug("Waiting for worker to be READY - Waiting seconds: %s" % (retry_count * retry_count))


def stop_run_condition():

    global RUN_CONDITION

    if RUN_CONDITION:
        RUN_CONDITION = False


def signal_handler(signum, frame):

    if signum == signal.SIGHUP:

        logging.info('Retrieved hang-up signal.')
        stop_run_condition()

    if signum == signal.SIGINT:

        logging.info('Retrieved interrupt program signal.')
        stop_run_condition()

    if signum == signal.SIGTERM:

        logging.info('Retrieved signal to terminate.')
        stop_run_condition()


def main():

    try:

        args = init_arg_parser()

        if args.print_version:
            print("Version %s" % VERSION)
            sys.exit()

        config_file_reader = ControllerConfigFileReader(args.config_file)

        init_logging(config_file_reader.log_filename, args.enable_debug)

        with PIDControl(config_file_reader.pid_file) as pid_control, \
                ControllerCommHandler(config_file_reader.comm_target,
                                      config_file_reader.comm_port,
                                      config_file_reader.poll_timeout) as comm_handler, \
                SharedQueue() as result_queue, \
                SharedQueue() as task_queue:

            if pid_control.lock():

                logging.info("Started")
                logging.info("Controller PID: %s", pid_control.pid())
                logging.debug("Version: %s" % VERSION)

                signal.signal(signal.SIGINT, signal.SIG_IGN)

                signal.signal(signal.SIGHUP, signal_handler)
                signal.signal(signal.SIGTERM, signal_handler)

                signal.siginterrupt(signal.SIGTERM, True)

                comm_handler.connect()

                request_retry_count = 0
                max_num_request_retries = 3
                request_retry_wait_duration = config_file_reader.request_retry_wait_duration

                lock_worker_state_table = multiprocessing.Lock()
                lock_result_queue = multiprocessing.Lock()

                cond_result_queue = multiprocessing.Condition(lock_result_queue)

                worker_count = config_file_reader.worker_count
                worker_ids = create_worker_ids(worker_count)
                worker_state_table = create_worker_state_table(worker_ids)

                worker_handle_dict = \
                    create_worker(worker_state_table,
                                  lock_worker_state_table,
                                  task_queue,
                                  result_queue,
                                  cond_result_queue)

                global RUN_CONDITION

                if not start_worker(worker_handle_dict, worker_state_table):

                    logging.error("Not all worker are ready!")
                    RUN_CONDITION = False

                while RUN_CONDITION:

                    try:

                        send_msg = None

                        if not send_msg:

                            with CriticalSection(cond_result_queue):

                                if not result_queue.is_empty():

                                    task_id = result_queue.pop_nowait()

                                    if task_id:

                                        logging.debug("Finished task: %s" % task_id)
                                        send_msg = TaskFinished(comm_handler.fqdn, task_id)

                        if not send_msg:

                            found_ready_worker = False

                            with CriticalSection(lock_worker_state_table):

                                for worker_id in worker_state_table.keys():

                                    if worker_handle_dict[worker_id].is_alive() \
                                            and worker_state_table[worker_id].get_state == WorkerState.READY:

                                        found_ready_worker = True
                                        break

                            if found_ready_worker:

                                logging.debug('Requesting a task...')

                                send_msg = TaskRequest(comm_handler.fqdn)

                            else:

                                worker_count = len(worker_state_table)
                                worker_count_not_active = 0

                                for worker_id in worker_state_table.keys():

                                    if not worker_handle_dict[worker_id].is_alive():
                                        worker_count_not_active += 1

                                if worker_count == worker_count_not_active:

                                    logging.error('No worker are alive!')
                                    RUN_CONDITION = False
                                    continue

                                else:   # Available worker are busy

                                    with CriticalSection(cond_result_queue):

                                        wait_timeout_result_queue = 1

                                        cond_result_queue.wait(wait_timeout_result_queue)

                                        if result_queue.is_empty():
                                            send_msg = Heartbeat(comm_handler.fqdn)

                        if send_msg:

                            logging.debug("Sending message to master: %s" % send_msg.to_string())
                            comm_handler.send_string(send_msg.to_string())

                            in_raw_data = comm_handler.recv_string()

                            if in_raw_data:

                                logging.debug("Retrieved message (raw data): " + in_raw_data)

                                in_msg = MessageFactory.create(in_raw_data)
                                in_msg_type = in_msg.type()

                                if MessageType.TASK_ASSIGN() == in_msg_type:

                                    task = in_msg.to_task()

                                    logging.debug("Retrieved task assign for: " + task.tid)

                                    task_queue.push(task)

                                    logging.debug("Pushed task to task queue: %s" % task.tid)

                                elif MessageType.ACKNOWLEDGE() == in_msg_type:
                                    continue

                                elif MessageType.WAIT_COMMAND() == in_msg_type:

                                    #TODO: Implement it on the master side!
                                    wait_duration = in_msg.duration
                                    logging.debug("Retrieved Wait Command with duration: " + str(wait_duration))
                                    time.sleep(wait_duration)

                                elif MessageType.EXIT_COMMAND() == in_msg_type:

                                    RUN_CONDITION = False
                                    logging.info('Retrieved exit message from master...')

                                # Reset after retrieving a message
                                if request_retry_count > 0:
                                    request_retry_count = 0

                            else:

                                if request_retry_count == max_num_request_retries:

                                    logging.info('Exiting, since maximum retry count is reached!')
                                    comm_handler.disconnect()
                                    RUN_CONDITION = False

                                time.sleep(request_retry_wait_duration)
                                logging.debug('No response retrieved - Reconnecting...')
                                comm_handler.reconnect()
                                request_retry_count += 1

                    except Exception as e:

                        RUN_CONDITION = False

                        exc_type, exc_obj, exc_tb = sys.exc_info()
                        filename = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]

                        logging.error("Caught exception (type: %s) in main loop: %s - %s (line: %s)"
                                      % (exc_type, str(e), filename, exc_tb.tb_lineno))

                if not RUN_CONDITION:

                    try:

                        logging.info("Shutting down all worker...")

                        all_worker_down = False

                        while not all_worker_down:

                            found_active_worker = False

                            for worker_id in worker_state_table.keys():

                                if worker_handle_dict[worker_id].is_alive():

                                    os.kill(worker_handle_dict[worker_id].pid, signal.SIGUSR1)

                                    task_queue.push(PoisenPill())

                                    logging.debug("Waiting for worker to complete: %s"
                                                  % worker_handle_dict[worker_id].name)

                                    found_active_worker = True

                            if not found_active_worker:
                                all_worker_down = True
                                logging.debug('All worker are down.')

                            else:
                                logging.debug('Waiting for worker to shutdown...')
                                time.sleep(1)

                    except Exception as e:
                        logging.error("Caught exception terminating Worker: " + str(e))

            else:

                logging.error("Another instance might be already running!")
                logging.info("PID file: %s" % config_file_reader.pid_file)
                sys.exit(1)

    except Exception as e:

        exc_type, exc_obj, exc_tb = sys.exc_info()
        filename = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        logging.error("Exception in %s (line: %s): %s" % (filename, exc_tb.tb_lineno, e))
        sys.exit(1)

    logging.info('Finished')
    sys.exit(0)


if __name__ == '__main__':
    main()
