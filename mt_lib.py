import base64
import threading
import time

import meshtastic
import meshtastic.serial_interface, meshtastic.tcp_interface

from meshtastic.protobuf import channel_pb2

from pubsub import pub


class MtHandler():
    def __init__(self, default_channel_index=1, reconnect_delay=5,
                 max_reconnect_delay=60, max_retries=None, on_connect=None):
        self.interface = None
        self.default_channel_index = default_channel_index

        # Reconnection settings
        self.reconnect_delay = reconnect_delay          # initial delay between attempts (s)
        self.max_reconnect_delay = max_reconnect_delay  # cap for exponential backoff (s)
        self.max_retries = max_retries                  # None = retry forever
        self.on_connect = on_connect                    # optional callback(self) after (re)connect

        self._connected = False
        self._closing = False
        self._generation = 0                            # bumped on every successful (re)connect
        self._reconnect_lock = threading.Lock()

        # The meshtastic library fires this when the serial/TCP link drops.
        pub.subscribe(self._on_connection_lost, "meshtastic.connection.lost")

    # --- to be provided by subclasses -------------------------------------
    def _create_interface(self):
        raise NotImplementedError

    def _target_desc(self):
        return "Meshtastic device"

    # --- connection management --------------------------------------------
    def connect(self):
        """Open the interface, retrying with exponential backoff until it succeeds."""
        attempt = 0
        delay = self.reconnect_delay
        while not self._closing:
            attempt += 1
            try:
                self.interface = self._create_interface()
                self._connected = True
                print(f"Connected to {self._target_desc()}")
                if self.on_connect:
                    try:
                        self.on_connect(self)
                    except Exception as e:
                        print(f"on_connect hook failed: {e}")
                return
            except Exception as e:
                self._connected = False
                print(f"Failed to connect to {self._target_desc()} (attempt {attempt}): {e}")
                if self.max_retries is not None and attempt >= self.max_retries:
                    raise
                print(f"Retrying in {delay} s...")
                time.sleep(delay)
                delay = min(delay * 2, self.max_reconnect_delay)

    def _on_connection_lost(self, interface=None):
        """pubsub callback (runs on the meshtastic reader thread)."""
        if self._closing:
            return
        # Ignore events from interfaces that aren't the one we currently hold.
        if interface is not None and self.interface is not None and interface is not self.interface:
            return
        print(f"Connection to {self._target_desc()} lost. Reconnecting...")
        # Reconnect on a separate thread so we don't block/recurse the dying reader thread.
        gen = self._generation
        threading.Thread(
            target=self.reconnect,
            kwargs={"expected_generation": gen},
            daemon=True,
        ).start()

    def reconnect(self, expected_generation=None):
        """Tear down the old interface and connect again.

        ``expected_generation`` lets concurrent callers (the lost-connection event
        and a failing send) collapse into a single reconnect: if another reconnect
        already completed while we waited for the lock, we simply return.
        """
        with self._reconnect_lock:
            if expected_generation is not None and self._generation != expected_generation:
                return  # already handled by another reconnect
            if self._closing:
                return

            self._connected = False
            old, self.interface = self.interface, None
            if old is not None:
                try:
                    old.close()
                except Exception:
                    pass

            self.connect()
            self._generation += 1

    def _ensure_connected(self):
        if self.interface is None or not self._connected:
            self.reconnect(expected_generation=self._generation)

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


    def sendMessage(self, message, channelIndex=None, hopLimit=3, max_attempts=3):
        """Send a text message (fire-and-forget).

        On a connection-level failure the send is retried up to ``max_attempts``
        times, reconnecting in between. Raises the last connection error if every
        attempt fails.
        """
        if channelIndex is None:
            channelIndex = self.default_channel_index

        last_err = None
        for attempt in range(max_attempts):
            self._ensure_connected()
            gen = self._generation

            try:
                self.interface.sendText(
                    text=message,
                    channelIndex=channelIndex,
                    hopLimit=hopLimit,
                )
                #print(f"Sent message: {message}")
                return
            except Exception as e:
                last_err = e
                print(f"Failed to send message (attempt {attempt + 1}/{max_attempts}): {e}")
                # Connection-level failure: reconnect (tied to this generation) and retry.
                self.reconnect(expected_generation=gen)

        if last_err is not None:
            raise last_err

class MtSerialHandler(MtHandler):
    def __init__(self, port='/dev/ttyUSB0', **kwargs):
        super().__init__(**kwargs)
        self.port = port
        self.interface = None

    def _create_interface(self):
        return meshtastic.serial_interface.SerialInterface(devPath=self.port)

    def _target_desc(self):
        return f"Meshtastic device at {self.port}"

    def disconnect(self):
        self._closing = True
        if self.interface:
            try:
                self.interface.close()
            except Exception:
                pass
            print(f"Disconnected from {self._target_desc()}")
        self.interface = None
        self._connected = False

class MtTcpHandler(MtHandler):
    def __init__(self, host='192.168.0.182', **kwargs):
        super().__init__(**kwargs)
        self.host = host
        self.interface = None

    def _create_interface(self):
        try:
            return meshtastic.tcp_interface.TCPInterface(hostname=self.host, timeout=10)
        except Exception as e:
            raise RuntimeError(f"nem hozható létre TCP interface: {e}") from e

    def _target_desc(self):
        return f"Meshtastic device at {self.host}"

    def disconnect(self):
        self._closing = True
        if self.interface:
            try:
                self.interface.close()
            except Exception:
                pass
            print(f"Disconnected from {self._target_desc()}")
        self.interface = None
        self._connected = False


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
        test_msg = f"Sending test message {i+1}"
        print(test_msg)
        mt.sendMessage(message=test_msg)
        time.sleep(60)
