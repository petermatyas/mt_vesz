import base64
import time

import meshtastic
import meshtastic.serial_interface, meshtastic.tcp_interface

from meshtastic.protobuf import channel_pb2


class MtHandler():
    def __init__(self, default_channel_index=1):
        self.interface = None
        self.default_channel_index = default_channel_index


    def setChannel(self, vesz_channel_name=None, edit_channel=None, new_settings=None):
        if vesz_channel_name is None:
            vesz_channel_name = 'vesz_teszt'

        if edit_channel is None:
            edit_channel = self.default_channel_index

        if new_settings is None:
            new_settings = {
                'psk': 'AQ==',
                'name': vesz_channel_name,
                'uplink_enabled': False,
                'downlink_enabled': True,
                'position_precision': 13
            }

        node = self.interface.getNode('^local')
        channel = node.channels[edit_channel]

        for key, value in new_settings.items():
            if key == 'psk':
                channel.settings.psk = base64.b64decode(value)
            elif key == 'position_precision':
                channel.settings.module_settings.position_precision = value
            else:
                setattr(channel.settings, key, value)

        if edit_channel == 0:
            channel.role = channel_pb2.Channel.Role.PRIMARY
        else:
            channel.role = channel_pb2.Channel.Role.SECONDARY

        node.writeChannel(edit_channel)
        #print(node.channels)

    def getChannel(self):
        node = self.interface.getNode('^local')
        channels = node.channels
        if channels:
            #print("Channels:")
            for channel in channels:
                if channel.role:
                    psk_base64 = base64.b64encode(channel.settings.psk).decode('utf-8')
                    #print(f"Index: {channel.index}, Role: {channel.role}, PSK (Base64): {psk_base64}, Name: {channel.settings.name}")
        else:
            #print("No channels found.")
            pass


    def sendMessage(self, message, channelIndex=None, hopLimit=3):
        if channelIndex is None:
            channelIndex = self.default_channel_index
        self.interface.sendText(text=message, channelIndex=channelIndex, hopLimit=hopLimit)
        #print(f"Sent message: {message}")

class MtSerialHandler(MtHandler):
    def __init__(self, port='/dev/ttyUSB0'):
        super().__init__()
        self.port = port
        self.interface = None

    def connect(self):
        try:
            self.interface = meshtastic.serial_interface.SerialInterface(devPath=self.port)
            print(f"Connected to Meshtastic device at {self.interface.devPath}")
        except Exception as e:
            print(f"Failed to connect to Meshtastic device: {e}")
            raise

    def disconnect(self):
        if self.interface:
            self.interface.close()
            print(f"Disconnected from Meshtastic device at {self.interface.devPath}")

class MtTcpHandler(MtHandler):
    def __init__(self, host='192.168.0.182'):
        super().__init__()
        self.host = host
        self.interface = None

    def connect(self):
        try:
            self.interface = meshtastic.tcp_interface.TCPInterface(hostname=self.host)
            print(f"Connected to Meshtastic device at {self.interface.hostname}:{self.interface.portNumber}")
        except Exception as e:
            print(f"Failed to connect to Meshtastic device: {e}")
            raise
    
    def disconnect(self):
        if self.interface:
            self.interface.close()
            print(f"Disconnected from Meshtastic device at {self.interface.hostname}:{self.interface.portNumber}")  


if __name__ == "__main__":
    mt = MtTcpHandler(host='192.168.0.182')
    mt.connect()
    mt.setChannel(vesz_channel_name='vesz_teszt', edit_channel=1, new_settings={
        'psk': 'AQ==',
        'name': 'vesz_teszt',       
        'uplink_enabled': False,
        'downlink_enabled': True,
        'position_precision': 13
    })
    for i in range(5):
        test_msg = f"Sending long long long long long long long long long long long long test message {i+1}"
        print(test_msg)
        mt.sendMessage(message=test_msg)
        time.sleep(60)


