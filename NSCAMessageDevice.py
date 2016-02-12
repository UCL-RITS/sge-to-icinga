import subprocess
import sys

class MessageDevice:
    """ Our abstracted messaging device, NSCA implementation

    Buffers and sends messages using the NSCA command client client.
    """

    def __init__(self,
                 config,
                 logger,
                 #nsca_send_command = "/usr/local/nagios/bin/send_nsca",
                 #nsca_send_command = "/send_nsca",
                 nsca_send_command = "/home/uccaiki/Code/opsview-gridengine-integration/shell_ver/send_nsca",
                 #nsca_config_file  = "/usr/local/nagios/etc/send_nsca.cfg"):
                 nsca_config_file  = "/home/uccaiki/Code/opsview-gridengine-integration/shell_ver/send_nsca.cfg"):
        self.logger = logger
        self.message_buffer = list()
        self.destination_host   = config["nsca_dest_host"]
        self.nsca_send_command  = nsca_send_command
        self.nsca_config_file   = nsca_config_file

    def add_message_to_buffer(self, message):
        self.message_buffer.append("message")
        pass

    def clear_message_buffer(self):
        self.message_buffer = list()

    def send_message_buffer(self):
        message = '\n'.join(self.message_buffer)
        self.send_one_message(message)
        self.clear_message_buffer()
        
    def send_one_message(self, message):
        try:
            messenger = subprocess.Popen(
                            [self.nsca_send_command, 
                             self.destination_host, 
                             "-c", 
                             "%s" % self.nsca_config_file], 
                            stdin=subprocess.PIPE,
                            )
            messenger.communicate(input=message)
        except:
            self.logger.error("could not send message: %s" % sys.exc_info()[1]) 
            pass
        else:
            self.logger.info("sent message.")

    def send_message_quads(self, message_quads):
        total_message = ('\n'.join(['\t'.join([str(y) for y in x]) for x in message_quads]) + "\n")
        with open("messages.view", "w") as f:
            f.write("%s\n" % total_message)
        self.send_one_message(total_message)
        pass
