#!/usr/bin/python

import argparse
import daemon
import logging
import operator
import re
import subprocess
import sys
import time
import yaml

from NSCAMessageDevice import MessageDevice
from IcingaService import IcingaService

def timeit(method):
    """ Decorator, for timing individual function calls if you want to do that
    """
    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()

        print '%r (%r, %r) %2.2f sec' % \
              (method.__name__, args, kw, te-ts)
        return result
    return timed

def get_command_output(command):
    """ Runs a command from the command_root, returns the output as a string.
    """
    command_root = "."
    process = subprocess.Popen(
            "%s/%s" % (command_root, command),
            stdout = subprocess.PIPE
            )
    (process_stdout, _) = process.communicate()
    return process_stdout

def get_sensor_comparator_dict():
    """ Takes a space-separated list of sensor names and operators from
    script, and converts into a dict { sensor_name: (<operator function>,type) }.
    """
    logger.info("getting sensor value operators.")
    thresholds = get_command_output("threshold_comparators.sh")
    ops_dict = dict()
    for line in thresholds.split("\n"):
        line_elements = line.split()
        if len(line_elements) == 3: # ignore blank lines
            ops_dict[line_elements[0]] = (cmp_op_from_string(line_elements[1]), line_elements[2])
    return ops_dict

def get_threshold_dict():
    """ Runs the script to get the thresholds, transforms it slightly
    into a dict with hostname keys.

    You could move this transformation into the script if it takes too long,
    I think.
    """
    logger.info("getting per-host threshold information.")
    thresholds_text = get_command_output("per-host-thresholds.yaml.sh")
    thresholds_list = list(yaml.load(thresholds_text))
    return { x["hostname"]: x for x in thresholds_list }

def cmp_op_from_string(operator_string):
    """ Takes a string containing an operator and returns the function that
    performs that operation.

    Intended to convert the operator column of the SGE load sensor table
    into the operation so that we can know how to compare the sensor data.
    """
    if operator_string == "<=":
        return operator.le
    elif operator_string == "==":
        return operator.eq
    elif operator_string == ">=":
        return operator.ge
    elif operator_string == ">":
        return operator.gt
    elif operator_string == "<":
        return operator.lt
    else:
        return None

def size_conv(size):
    """ Converts numbers with binarised SI suffixes into real numbers.
    """
    if size == 0 or size == "0":
        return 0
    convs = { "K": 1024,
              "M": 1024*1024,
              "G": 1024*1024*1024,
              "T": 1024*1024*1024*1024
              }
    try:
        value = float(size[0:-1]) * convs[size[-1:]]
    except:
        logger.error("could not convert value to float: %s" % size)
    return value

def compare_datum(datum, threshold, operator_tuple):
    """ Compares the datum to the threshold using the operator.

    Assumes operator_tuple[0] is a function to compare the two,
    and operator_tuple[1] is an SGE type (which only matters if
    it has to convert from a MEMORY type which can have SI suffixes.
    """
    if operator_tuple[1] == "MEMORY":
        datum = size_conv(datum)
        threshold = size_conv(threshold)
    result = operator_tuple[0](datum, threshold)
    if result == True:
        result = 2
    else:
        result = 0
    return result

def transform_errors_to_dict(error_list):
    """ The errors come out of the qstat wrap as a list: this tries to
    transform them into a dictionary with the keys being the sensor_name
    referenced.

    It has a limited knowledge of the possible errors though.
    """

    error_dict = dict()
    #   error: no complex attribute for threshold micproblems
    #   error: no value for "micproblems" because execd is in unknown state
    execd_broke_re = re.compile("^no value for \"(?P<sensor_name>[^\"]*)\" because execd is in unknown state$")
    no_attribute_re = re.compile("^no complex attribute for threshold (?P<sensor_name>.*)$")
    for error in error_list:
        match = execd_broke_re.match(error)
        if match is None:
            match = no_attribute_re.match(error)
        if match is None:
            logger.warn("could not pattern match error: %s" % error)
        sensor_name = match.group("sensor_name")
        error_dict[sensor_name] = error
    return error_dict

def check_data_against_thresholds(thresholds, comparators):
    """ Main comparison routine, where the daemon will spend its non-sleep
    time.

    Tries to avoid storing more than one host's worth of data, to keep
    memory usage down.

    It's kind of fiddly because this whole thing is a disgusting hack.

    Such a disgusting inelegant hack that requires other disgusting inelegant hacks that it makes me angry.
    """

    logger.info("getting sensor data from qstat.")
    time_start = time.time()
    #host_data_text = get_command_output("qstat-explain.yaml.sh")
    host_data_text = get_command_output("qhost-F.yaml.sh")
    time_stop = time.time()
    logger.info("got sensor data from qstat in %d s." % (time_stop - time_start))

    logger.info("comparing data to thresholds.")
    time_start = time.time()

    host_doc_generator = yaml.load_all(host_data_text)

    messages = list()
    for host_data in host_doc_generator:
        hostname = host_data["hostname"]
        if hostname == "global":
            # Skip global because there's no threshold data for it
            #  and getting it at all is just a by-product
            continue
        if not thresholds.has_key(hostname):
            # Then there's nothing useful we can do here.
            # Occurs when hosts are down or have no queues defined.
            continue

        if host_data.has_key("errors"):
            host_data["errors"] = transform_errors_to_dict(host_data["errors"])
        else:
            host_data["errors"] = dict()
            # ^-- adding an empty dict makes life easier for checking
        for k in comparators.keys():
            if ((k[-7:] != "_nagtxt") and
                comparators.has_key("%s_nagtxt" % k) and
                not k in ["hostname","qname"]):
                
                if thresholds[hostname].has_key(k) and host_data.has_key(k):
                    result = compare_datum(host_data[k], thresholds[hostname][k], comparators[k])
                else:
                    result = 0

                # To make Nagios perfdata understand the type, see: https://nagios-plugins.org/doc/guidelines.html#AEN200
                if comparators[k][1] == "MEMORY":
                    append_to_value = "B"
                else: 
                    append_to_value = ""

                if host_data.has_key("%s_nagtxt" % k) and host_data.has_key(k):
                    data_string = "%s|%s=%s%s" % (host_data["%s_nagtxt" % k], k, str(host_data[k]), append_to_value)
                elif host_data.has_key(k):
                    data_string = "%s%s|%s=%s%s" % (host_data[k], append_to_value, k, str(host_data[k]), append_to_value)
                elif host_data["errors"].has_key(k):
                    result = 2
                    data_string = host_data["errors"][k]
                else:
                    data_string = "0"
                messages.append((hostname, k, result, data_string))

    time_stop = time.time()
    logger.info("prepared message quads from data comparison in %d s." % (time_stop - time_start))
    return messages

def size_of_messages(messages):
    """ Gets the size of a container of containers of things.

    Used for printing out how much RAM the messages list is using.
    """
    s = sys.getsizeof

    return (s(messages) + 
            sum( [ s(x) for x in messages ] ) +
            sum( [ sum([s(y) for y in x]) for x in messages] )
            ) 

def make_hosts_services_dict(messages):
    """Makes a dict containing which services each host needs on the monitoring
    platform: intended to be used to generate Icinga calls.
    """

    hosts_services_dict = { x[0]: [y[1] for y in messages if y[0]==x[0] ] for x in messages }
    return hosts_services_dict

class MessageMaker:
    """ Brings all of the above together into one thing that makes the NSCA
    messages.
    """
    def __init__(self):
        self.comparators = get_sensor_comparator_dict()
        self.thresholds = get_threshold_dict()
        # set up the sender process here?

    def make(self):
        messages = check_data_against_thresholds(self.thresholds, self.comparators)
        logger.info("holding message quad list in %d bytes." % 
                    size_of_messages(messages))
        return messages 


class MessageMakerDaemon:
    """ Wraps a MessageMaker instance into a daemon.
    """
    def __init__(self, config, log_file_handle):
        self.message_maker = MessageMaker()
        self.log_file_handle = log_file_handle
        self.config = config
        self.icinga_service = IcingaService(config, logger)
        self.message_device = MessageDevice(config, logger)

    def start(self, run_in_foreground):
        logger.info("starting daemon.")
        if run_in_foreground == False:
            self.context = daemon.DaemonContext()
            self.context.files_preserve = [fh.stream]
            self.context.open()

            try:
                self.loop(self.config["check_interval"])
            finally:
                context.close()
        else:
            self.loop(self.config["check_interval"])
        pass

    def loop(self, interval):
        while True:
            messages = self.message_maker.make()
            hosts_services_dict = make_hosts_services_dict(messages)
            self.icinga_service.ensure_hosts_exist(hosts_services_dict)

            self.message_device.send_message_quads(messages)
            logger.info("sleeping for %d seconds..." % interval)
            time.sleep(interval)


###########
# End of internal gubbins, beginning of interface.

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Daemon to pull sensor information from SGE and push it to send_nsca.')
    parser.add_argument("-c", "--config", metavar="file", dest='config_file', default="./config.yaml", help="Supply YAML configuration file")
    parser.add_argument("-f", "--foreground", action='store_true', dest='run_in_foreground', default=False, help="Don't daemonize; run in foreground.")
    parser.add_argument("--make-config", action='store_true', dest="make_config", default=False, help="Print default config file.")
    if not argv is None:
        return parser.parse_args()
    else:
        return parser.parse_args(argv)

def get_config_from_file(filename):
    try:
        with open(filename, 'r') as config_file:
            config = yaml.load_all(config_file).next()
    except :
        logger.error("failed to read config file, exiting.")
        sys.exit(2)

    must_have_keys = list(["icinga_server", "icinga_username", "icinga_password", "nsca_dest_host"])
    optional_keys = { "check_interval": 120,
                      "log_level": "INFO",
                      "log_file": "/var/log/sge_to_icinga.log",
                      "message_copy": False }

    for key in must_have_keys:
        if not key in config.keys():
            logger.error("mandatory key not found in config file: %s" % key)
            sys.exit(2)

    for key in optional_keys.keys():
        if not key in config.keys():
            config[key] = optional_keys[key]

    for key in config.keys():
        if ((not key in must_have_keys) and
            (not key in optional_keys.keys())):
            logger.error("unrecognised key in config file: %s" % key)
            sys.exit(2)

    return config

def print_default_config_file():
    sys.stdout.write("check_interval: 120\n" +
                     "log_file: /var/log/sge_to_icinga.log\n" +
                     "log_level: INFO\n" +
                     "message_copy: /var/log/message_copy\n" +
                     "icinga_server: localhost\n" +
                     "icinga_username: icinga\n" +
                     "icinga_password: icinga\n" +
                     "nsca_dest_host: localhost\n"
                     )
    pass

def configure_logger_returning_log_file_handle(args, config):

    logger.setLevel(config["log_level"])

    frmt = logging.Formatter('%(name)s - %(asctime)s - %(levelname)s: %(message)s')

    if not (args.run_in_foreground or args.make_config):
        fh = logging.FileHandler(config["log_file"])
    else:
        fh = logging.StreamHandler()

    logger.addHandler(fh)
    fh.setFormatter(frmt)
    return fh

def main():
    args = parse_args()

    # We set up a temporary logger here in case the config reading fails.
    temp_handle = logging.StreamHandler()
    logger.addHandler(temp_handle)
    config = get_config_from_file(args.config_file)
    logger.removeHandler(temp_handle)

    log_file_handle = configure_logger_returning_log_file_handle(args, config)
    # ^-- this needs to get explicitly preserved by the daemon setup
    #     all other file handles get closed

    if args.make_config:
        print_default_config_file()
        sys.exit(0)

    # Only option left is run daemon
    d = MessageMakerDaemon(config, log_file_handle)
    d.start(args.run_in_foreground)
    sys.stderr.write("Program should not reach this point. Eep.\n")
    sys.exit(2)

if __name__ == "__main__":
    logger = logging.getLogger("SGE2NSCA")
    # ^-- GLOBAL SCOPE
    main()
