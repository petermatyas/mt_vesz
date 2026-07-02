"""Soros (USB) port felderítő. Linuxon és Windowson is működik.

Kigyűjti az elérhető soros portokat a pyserial segítségével, és kiírja
a legfontosabb adataikat (eszköz neve, leírás, hardver azonosító).

Használat:
    python list_ports.py
"""

import sys

try:
    from serial.tools import list_ports
except ImportError:
    print("Hiányzik a pyserial csomag. Telepítés: pip install pyserial")
    sys.exit(1)


def find_ports():
    """Az összes felismert soros portot adja vissza pyserial ListPortInfo listaként."""
    return sorted(list_ports.comports(), key=lambda p: p.device)


def main():
    ports = find_ports()

    if not ports:
        print("Nem található aktív soros port.")
        return

    print(f"Talált soros portok száma: {len(ports)}\n")
    for p in ports:
        print(f"Eszköz:      {p.device}")
        print(f"  Leírás:    {p.description}")
        print(f"  HWID:      {p.hwid}")
        if p.manufacturer:
            print(f"  Gyártó:    {p.manufacturer}")
        if p.vid is not None and p.pid is not None:
            print(f"  VID:PID:   {p.vid:04X}:{p.pid:04X}")
        if p.serial_number:
            print(f"  Sorozatsz: {p.serial_number}")
        print()


if __name__ == "__main__":
    main()
