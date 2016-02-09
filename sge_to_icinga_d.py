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
    """ Main comparison routine, where the daemon will spend move its non-sleep
    time.

    Tries to avoid storing more than one host's worth of data, to keep
    memory usage down.

    It's kind of fiddly because this whole thing is a disgusting hack.
    """

    logger.info("getting sensor data from qstat.")
    host_data_text = get_command_output("qstat-explain.yaml.sh")
    logger.info("comparing data to thresholds.")
    
    host_doc_generator = yaml.load_all(host_data_text)
   
    messages = list()
    for host_data in host_doc_generator:
        hostname = host_data["hostname"]
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

                if host_data.has_key("%s_nagtxt" % k) and host_data.has_key(k):
                    data_string = "%s |%s" % (str(host_data[k]), host_data["%s_nagtxt" % k])
                elif host_data.has_key(k):
                    data_string = str(host_data[k])
                elif host_data["errors"].has_key(k):
                    result = 2
                    data_string = host_data["errors"][k]
                else:
                    data_string = "0"
                messages.append("%s %s %d %s" % (hostname, k, result, data_string))

    logger.info("prepared message output from data comparison.")
    print '\n'.join(messages)
    # ^-- TODO: send to NSCA
    logger.info("finished round of message output.")


class MessageMaker:
    """ Brings all of the above together into one thing that makes the NSCA
    messages.
    """
    def __init__(self):
        self.comparators = get_sensor_comparator_dict()
        self.thresholds = get_threshold_dict()
        # set up the sender process here?

    def make(self):
        check_data_against_thresholds(self.thresholds, self.comparators)

class MessageMakerDaemon:
    """ Wraps a MessageMaker instance into a daemon.
    """
    def __init__(self, config, log_file_handle):
        self.message_maker = MessageMaker()
        self.log_file_handle = log_file_handle
        self.config = config

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
            self.message_maker.make()
            time.sleep(interval)


###########
# End of internal gubbins, beginning of interface.

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Daemon to pull sensor information from SGE and push it to send_nsca.')
    parser.add_argument("-c", "--config", metavar="file", dest='config_file', default="./config.yaml", help="Supply YAML configuration file")
    parser.add_argument("-f", "--foreground", action='store_true', dest='run_in_foreground', default=False, help="Don't daemonize; run in foreground.")
    parser.add_argument("-s", "--sync", action='store_true', dest="sync", default=False, help="Only synchronise host list.")
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

    must_have_keys = list()
    optional_keys = { "check_interval": 120,
                      "log_level": "INFO",
                      "log_file": "/var/log/sge_to_icinga.log" }

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
                     "log_level: INFO\n" + 
                     "log_file: /var/log/sge_to_icinga.log\n")
    pass

def configure_logger_returning_log_file_handle(args, config):

    logger.setLevel(config["log_level"])

    frmt = logging.Formatter('%(module)s - %(asctime)s - %(levelname)s: %(message)s')

    if args.run_in_foreground or args.make_config or args.sync:
       fh = logging.StreamHandler()
    else:
       fh = logging.FileHandler(config["log_file"])

    fh.setFormatter(frmt)
    logger.addHandler(fh)

    return fh

def main():
    args = parse_args()
    config = get_config_from_file(args.config_file)
    
    log_file_handle = configure_logger_returning_log_file_handle(args, config)
    # ^-- this needs to get explicitly preserved by the daemon setup
    #     all other file handles get closed

    if args.make_config and args.sync:
        logger.error("incompatible options specified, exiting.")
        sys.exit(2)

    if args.make_config:
        print_default_config_file()
        sys.exit(0)

    if args.sync:
        # TODO: this
        sys.exit(0)
        pass

    # Only option left is run daemon
    d = MessageMakerDaemon(config, log_file_handle)
    d.start(args.run_in_foreground)
    sys.stderr.write("Program should not reach this point. Eep.\n")
    sys.exit(2)

if __name__ == "__main__":
    logger = logging.getLogger("SGE2NSCA")
    # ^-- GLOBAL SCOPE
    main()