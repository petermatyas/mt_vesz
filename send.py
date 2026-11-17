"""Tetszőleges szöveges üzenet küldése egy tetszőleges csatornára.

A config.toml [meshtastic] szekcióját használja (kapcsolódás, hop_limit, nyugta),
így ugyanúgy küld, mint a hírküldés (main.py) és az életjel (heartbeat.py).
A csatornát NEM állítja be: csak olyan csatornára küld, ami a node-on már
létezik (lásd setup_channel.py, ill. `meshtastic --ch-add`).

Használat:
    python send.py "Az üzenet szövege"              # a vészhelyzeti csatornára
    python send.py --channel 2 "Az üzenet szövege"  # a 2-es indexű csatornára
    python send.py --list                           # a node csatornáinak listája
    python send.py --no-log-text "..."              # a logba nem kerül be a szöveg

Kilépési kód: 0 = elküldve, 1 = hiba (csatlakozás, érvénytelen csatorna, túl hosszú üzenet).
"""

import argparse
import logging
import sys

from meshtastic.protobuf import channel_pb2, mesh_pb2

from main import cfg, build_handler


logger = logging.getLogger(__name__)

# Egy Meshtastic csomag hasznos terhének felső korlátja (bájt).
PAYLOAD_LIMIT = getattr(mesh_pb2.Constants, "DATA_PAYLOAD_LEN", 233)

ROLE_NAMES = {
    channel_pb2.Channel.Role.PRIMARY: "PRIMARY",
    channel_pb2.Channel.Role.SECONDARY: "SECONDARY",
}


class _RedactText(logging.Filter):
    """Az üzenet szövegét "<rejtett>"-re cseréli a log rekordok argumentumaiban,
    hogy a küldött szöveg ne kerüljön be a logfájlba."""

    def __init__(self, text):
        super().__init__()
        self.text = text

    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple("<rejtett>" if a == self.text else a for a in record.args)
        return True


def parse_args():
    p = argparse.ArgumentParser(description="Üzenet küldése tetszőleges Meshtastic csatornára.")
    p.add_argument("message", nargs="*", help="az üzenet szövege (több szó idézőjel nélkül is megadható)")
    p.add_argument("-c", "--channel", type=int, default=None,
                   help="a csatorna indexe 0-7 (alapértelmezés: meshtastic.emergency_channel_number)")
    p.add_argument("--list", action="store_true", help="kilistázza a node csatornáit, és kilép")
    p.add_argument("--no-ack", action="store_true", help="nem várja meg a nyugtát (felülírja a want_ack beállítást)")
    p.add_argument("--no-log-text", action="store_true", help="a küldött szöveg nem kerül be a logba")
    return p.parse_args()


def get_channels(mt):
    """A node beállított (nem DISABLED) csatornái: {index: (szerep, név)}."""
    result = {}
    for ch in mt.interface.localNode.channels or []:
        if ch.role == channel_pb2.Channel.Role.DISABLED:
            continue
        name = ch.settings.name or "(alapértelmezett)"
        result[ch.index] = (ROLE_NAMES.get(ch.role, str(ch.role)), name)
    return result


def main():
    args = parse_args()
    message = " ".join(args.message).strip()
    channel = args.channel if args.channel is not None else cfg("meshtastic.emergency_channel_number", 1)

    if not args.list:
        if not message:
            raise SystemExit("Hiba: nincs megadva üzenet. Használat: python send.py [--channel N] \"szöveg\"")
        if not 0 <= channel <= 7:
            raise SystemExit(f"Hiba: a csatorna indexe 0 és 7 között lehet (megadva: {channel}).")
        size = len(message.encode("utf-8"))
        limit = cfg("vesz.max_message_length", 0) or PAYLOAD_LIMIT
        limit = min(limit, PAYLOAD_LIMIT)
        if size > limit:
            raise SystemExit(f"Hiba: az üzenet túl hosszú ({size} bájt, legfeljebb {limit}). "
                             "Ékezetes betű 2 bájt.")
        if args.no_log_text:
            for name in ("mt_lib", __name__):
                logging.getLogger(name).addFilter(_RedactText(message))

    mt = build_handler()
    try:
        mt.connect()
    except Exception as e:
        logger.error("Nem sikerült csatlakozni a node-hoz: %s", e)
        raise SystemExit(f"Hiba: nem sikerült csatlakozni a node-hoz: {e}")

    try:
        exit_code = run(mt, args, message, channel)
    except Exception as e:
        logger.error("Üzenet küldése sikertelen: %s", e)
        print(f"Hiba: az üzenet küldése sikertelen: {e}", file=sys.stderr)
        exit_code = 1
    finally:
        try:
            mt.disconnect()
        except Exception as e:
            logger.error("Lecsatlakozás sikertelen: %s", e)

    raise SystemExit(exit_code)


def run(mt, args, message, channel):
    """A csatlakozott node-on elvégzi a listázást vagy a küldést. Visszaadja a kilépési kódot."""
    channels = get_channels(mt)

    if args.list:
        for idx, (role, name) in sorted(channels.items()):
            print(f"{idx}: {name} [{role}]")
        return 0

    if channel not in channels:
        available = ", ".join(f"{i} ({n})" for i, (_, n) in sorted(channels.items())) or "nincs"
        logger.error("A(z) %d. csatorna nincs beállítva a node-on.", channel)
        print(f"Hiba: a(z) {channel}. csatorna nincs beállítva a node-on. Elérhető: {available}",
              file=sys.stderr)
        return 1

    want_ack = cfg("meshtastic.want_ack", False) and not args.no_ack
    logger.info("Kézi üzenet küldése a(z) %d. csatornára (%s): %r",
                channel, channels[channel][1], message)
    mt.sendMessage(
        message,
        channelIndex=channel,
        hopLimit=cfg("meshtastic.hop_limit", 3),
        want_ack=want_ack,
        ack_timeout_s=cfg("meshtastic.ack_timeout_s", 30),
        ack_max_retries=cfg("meshtastic.ack_max_retries", 2),
    )
    print(f"Elküldve a(z) {channel}. csatornára ({channels[channel][1]}).")
    return 0


if __name__ == "__main__":
    main()
