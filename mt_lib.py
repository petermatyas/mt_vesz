import base64
import logging
import threading
import time

import meshtastic
import meshtastic.serial_interface, meshtastic.tcp_interface

from meshtastic.protobuf import channel_pb2, portnums_pb2

from pubsub import pub


logger = logging.getLogger(__name__)


class _AckWaiter:
    """Egyetlen küldés nyugtájára (ACK / NAK) vár.

    A meshtastic könyvtár a saját olvasó szálán hívja az ``on_ack_nak``
    callbacket, amikor a küldött csomag packet ID-jára hivatkozó "routing"
    csomag megérkezik. Az eredményt egy ``threading.Event``-en keresztül adjuk
    át a küldő szálnak.
    """

    # Lehetséges eredmények
    ACK = "ack"                    # egy másik node visszaigazolta a vételt
    IMPLICIT_ACK = "implicit_ack"  # egy szomszéd továbbadta (rebroadcast) a csomagot
    NAK = "nak"                    # a hálózat feladta a kézbesítést

    def __init__(self, local_node_num=None):
        # A saját node számunk kell az implicit ACK felismeréséhez; ha nem
        # ismerjük, nem tudjuk megkülönböztetni a valódi ACK-tól.
        self.local_node_num = local_node_num
        self.result = None
        self.error_reason = None
        self._event = threading.Event()

    def on_ack_nak(self, packet=None):
        try:
            routing = ((packet or {}).get("decoded") or {}).get("routing") or {}
            reason = routing.get("errorReason", "NONE")
            if reason != "NONE":
                self.result = self.NAK
                self.error_reason = reason
            elif (self.local_node_num is not None
                    and int(packet.get("from", -1)) == self.local_node_num):
                # A saját node-unk küldte a nyugtát: hallotta, hogy egy szomszéd
                # megismételte a csomagot.
                self.result = self.IMPLICIT_ACK
            else:
                self.result = self.ACK
        except Exception as e:
            logger.error("A nyugta feldolgozása sikertelen: %s", e)
        finally:
            self._event.set()

    def wait(self, timeout_s):
        """Megvárja a nyugtát; visszaadja az eredményt, vagy None, ha időtúllépés."""
        self._event.wait(timeout_s)
        return self.result


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
                logger.info("Connected to %s", self._target_desc())
                if self.on_connect:
                    try:
                        self.on_connect(self)
                    except Exception as e:
                        logger.error("on_connect hook failed: %s", e)
                return
            except Exception as e:
                self._connected = False
                logger.error("Failed to connect to %s (attempt %d): %s",
                             self._target_desc(), attempt, e)
                if self.max_retries is not None and attempt >= self.max_retries:
                    raise
                logger.info("Retrying in %d s...", delay)
                time.sleep(delay)
                delay = min(delay * 2, self.max_reconnect_delay)

    def _on_connection_lost(self, interface=None):
        """pubsub callback (runs on the meshtastic reader thread)."""
        if self._closing:
            return
        # Ignore events from interfaces that aren't the one we currently hold.
        if interface is not None and self.interface is not None and interface is not self.interface:
            return
        logger.warning("Connection to %s lost. Reconnecting...", self._target_desc())
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


    def _send_raw(self, message, channelIndex, hopLimit, max_attempts,
                  want_ack=False, on_response=None):
        """A tényleges rádiós küldés, kapcsolat-szintű újrapróbálkozással.

        Kapcsolati hiba (a küldés kivételt dob – pl. megszakadt TCP/serial link)
        esetén legfeljebb ``max_attempts``-szor próbálkozik, közben
        újracsatlakozik. Ha minden próba elbukik, az utolsó hibát dobja.
        A nyugtát nem várja meg – azt a hívó ``sendMessage`` intézi.

        Visszaadja az elküldött csomagot (az ``id`` mezőben a packet ID-val).

        A magasabb szintű ``sendText`` helyett ``sendData``-t hívunk, mert csak
        ez ismeri az ``onResponseAckPermitted`` kapcsolót: enélkül a könyvtár a
        sikeres ACK-okat eldobná, és csak a NAK-ot adná át a callbacknek."""
        last_err = None
        for attempt in range(max_attempts):
            self._ensure_connected()
            gen = self._generation

            try:
                packet = self.interface.sendData(
                    message.encode("utf-8"),
                    portNum=portnums_pb2.PortNum.TEXT_MESSAGE_APP,
                    channelIndex=channelIndex,
                    hopLimit=hopLimit,
                    wantAck=want_ack,
                    onResponse=on_response,
                    onResponseAckPermitted=True,
                )
                # Sikeres átadás a rádiónak – naplózzuk (csatorna + üzenet).
                logger.info("Üzenet elküldve (csatorna %d): %r", channelIndex, message)
                return packet
            except Exception as e:
                last_err = e
                logger.error("Failed to send message (attempt %d/%d): %s",
                             attempt + 1, max_attempts, e)
                # Connection-level failure: reconnect (tied to this generation) and retry.
                self.reconnect(expected_generation=gen)

        if last_err is not None:
            raise last_err

    def _local_node_num(self):
        """A saját node száma (az implicit ACK felismeréséhez), vagy None."""
        try:
            return self.interface.localNode.nodeNum
        except Exception:
            return None

    def _drop_response_handler(self, packet):
        """A nyugtára váró callback eldobása időtúllépés után.

        Ha a nyugta sosem érkezik meg, a könyvtár a callbacket a packet ID-hoz
        rendelve megtartaná – folyamatos (schedule) módban ez korlátlanul nőne."""
        try:
            self.interface.responseHandlers.pop(packet.id, None)
        except Exception:
            pass

    def sendMessage(self, message, channelIndex=None, hopLimit=3, max_attempts=3,
                    want_ack=False, ack_timeout_s=30, ack_max_retries=2):
        """Szöveges üzenet küldése.

        Ha ``want_ack`` hamis: "tűzd ki és felejtsd el" – csak kapcsolati hiba
        esetén próbálkozik újra (``max_attempts``).

        Ha ``want_ack`` igaz, a csomag ``wantAck`` jelzővel megy ki, és a küldés
        megvárja a nyugtát, legfeljebb ``ack_timeout_s`` másodpercig. Nyugta
        (vagy NAK) hiányában az üzenetet újraküldi, összesen legfeljebb
        ``ack_max_retries`` alkalommal (tehát max. ``1 + ack_max_retries``
        küldés). A nyugta háromféle lehet:

        - ACK: egy másik node visszaigazolta a vételt (csak címzett üzenetnél).
        - implicit ACK: broadcastnál (csatornára szórt hír) ez az egyetlen
          elérhető pozitív jelzés – a node hallotta, hogy egy szomszéd
          továbbadta a csomagot. Nem garancia a kézbesítésre, de azt mutatja,
          hogy az üzenet kijutott a mesh-be.
        - NAK: a firmware feladta a kézbesítést (``errorReason`` az okot adja).

        FIGYELEM: az újraküldés **új packet ID-t** kap, amit a vevő node-ok nem
        deduplikálnak – ha az eredeti üzenet mégis megérkezett (csak a nyugta
        veszett el), a hallgatóknál duplikátum jelenhet meg. Ezért tartsd az
        ``ack_max_retries`` értékét alacsonyan. A firmware saját, packet ID
        szintű újraadása ettől függetlenül, duplikátum nélkül működik."""
        if channelIndex is None:
            channelIndex = self.default_channel_index

        if not want_ack:
            self._send_raw(message, channelIndex, hopLimit, max_attempts)
            return

        total_rounds = 1 + max(0, ack_max_retries)
        for round_no in range(1, total_rounds + 1):
            waiter = _AckWaiter(self._local_node_num())
            packet = self._send_raw(message, channelIndex, hopLimit, max_attempts,
                                    want_ack=True, on_response=waiter.on_ack_nak)

            result = waiter.wait(ack_timeout_s)

            if result == _AckWaiter.ACK:
                logger.info("Nyugta megérkezett (ACK): a címzett vette az üzenetet.")
                return
            if result == _AckWaiter.IMPLICIT_ACK:
                logger.info("Implicit nyugta: egy szomszéd node továbbadta az üzenetet "
                            "(a kézbesítés valószínű, de nem garantált).")
                return
            if result == _AckWaiter.NAK:
                logger.warning("A hálózat elutasította az üzenetet (NAK, ok: %s) "
                               "[%d/%d próba].", waiter.error_reason, round_no, total_rounds)
            else:
                self._drop_response_handler(packet)
                logger.warning("Nem érkezett nyugta %d másodpercen belül [%d/%d próba].",
                               ack_timeout_s, round_no, total_rounds)

        logger.error("Az üzenet %d próbálkozás után sem kapott nyugtát: %r",
                     total_rounds, message)

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
