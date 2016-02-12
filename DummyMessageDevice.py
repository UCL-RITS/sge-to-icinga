import sys

class MessageDevice:
    """ Dummy message device that just prints all messages that would be sent
    to stdout, with trace info.
    """
    def __init__(self, _a, _b=None, _c=None):
        self.message_buffer = list()

    def add_message_to_buffer(self, message):
        self.message_buffer.append(message)
        pass

    def clear_message_buffer(self):
        self.message_buffer = list()

    def send_message_buffer(self):
        message = '\n'.join(self.message_buffer)
        self.send_one_message(message)
        self.clear_message_buffer()
        
    def send_one_message(self, message):
        sys.stdout.write(message)

    def make_messages(self, list_of_lists):
        messages = list()
        for one_message_data in list_of_lists:
            if len(one_message_data) == 4:
                self.add_message_to_buffer('\t'.join(one_message_data))
            else:
                self.add_message_to_buffer(
                        '\t'.join(
                            one_message_data[0:4] +
                            [ ' |'.join(one_message_data[4:])]
                            )
                        )

    def send_message_quads(self, message_quads):
        self.send_one_message('\n'.join([' '.join([str(y) for y in x]) for x in message_quads]))
        pass
