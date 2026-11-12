"""Regenerates synthetic_nmea.txt. SYNTHETIC: every MMSI is 99900000x (MID 999 does not exist), every name is made up.
No real AIS data and no real vessel identity is committed here (data is never committed).
Line format: "<unix epoch seconds> <NMEA sentence>"; a line with no epoch exercises the missing-time report.
Run: python tests/fixtures/ais/make_fixture.py > tests/fixtures/ais/synthetic_nmea.txt"""
import math

from pyais.encode import encode_dict

T0 = 1704844800                      # 2024-01-10T00:00:00Z
BASE = (5.30, 60.40)
DLON_PER_MIN = 12 * 1852 / 60 / (111_320 * math.cos(math.radians(BASE[1])))   # degrees lon per minute at 12 kn


def cs(body):
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f"{c:02X}"


def fix(s):                          # pyais emits AIVDO (own ship); a shore receiver sees AIVDM
    body = s[1:s.rindex("*")].replace("AIVDO", "AIVDM")
    return f"!{body}*{cs(body)}"


def pos(mmsi, lon, lat, sog, cog, sec, typ=1):
    d = dict(msg_type=typ, mmsi=str(mmsi), lon=lon, lat=lat, speed=sog, course=cog, heading=int(cog) % 360, second=sec % 60,
             accuracy=1, turn=0, status=0 if sog > 1 else 5, maneuver=0, raim=0, radio=0)
    return [fix(x) for x in encode_dict(d, radio_channel="A")]


def main():
    out = []
    t, lon = T0, BASE[0] + DLON_PER_MIN * 60
    for _ in range(12):              # vessel 1 inbound at 12 kn, fixes every 5 min
        out += [f"{t} {s}" for s in pos(999000001, lon, BASE[1], 12.0, 270.0, t)]
        t += 300
        lon -= DLON_PER_MIN * 5
    for k in range(25):              # 2 h alongside (jitter 15 m), 0.1 kn
        out += [f"{t} {s}" for s in pos(999000001, BASE[0] + 0.0002 * (k % 2), BASE[1], 0.1, 0.0, t)]
        t += 300
    for i in range(12):              # outbound
        out += [f"{t} {s}" for s in pos(999000001, BASE[0] - DLON_PER_MIN * 5 * (i + 1), BASE[1], 12.0, 270.0, t)]
        t += 300
    st = dict(msg_type=5, mmsi="999000001", shipname="TESTVESSEL ONE", callsign="TST1", ship_type=70, imo=9999999,
              draught=6.5, to_bow=40, to_stern=40, to_port=8, to_starboard=8, destination="BASE", epfd=1, ais_version=0)
    p5 = [fix(x) for x in encode_dict(st, radio_channel="A", seq_id=3)]
    out += [f"{T0 + 60} {p5[0]}"]
    out += [f"{T0 + 61} {s}" for s in pos(999000002, 5.6, 60.5, 8.0, 90.0, 1, typ=2)]     # interleaved between fragments
    out += [f"{T0 + 62} {p5[1]}"]
    for k in range(6):               # vessel 2 passes by, type 3
        out += [f"{T0 + 600 * k} {s}" for s in pos(999000002, 5.6 + 0.01 * k, 60.5, 8.0, 90.0, k, typ=3)]
    good = pos(999000001, 5.31, 60.40, 11.0, 270.0, 5)[0]
    out += [f"{T0 + 7200} {good[:-2]}00"]                                        # bad checksum
    out += [f"{T0 + 7201} not an nmea sentence"]                                  # garbage
    out += [f"{T0 + 7202} {pos(999000003, 181.0, 91.0, 5.0, 10.0, 7)[0]}"]        # position not available
    out += [f"{T0 + 7203} {[fix(x) for x in encode_dict(dict(msg_type=5, mmsi='999000004', shipname='LONELY', ship_type=70), radio_channel='B', seq_id=5)][0]}"]  # fragment 1 of 2, never completed
    out += [good]                                                                  # no epoch
    out += [f"{T0 + 7204} {fix(encode_dict(dict(msg_type=18, mmsi='999000005', lon=5.4, lat=60.4, speed=3.0, course=10.0, heading=10, second=9, accuracy=1, raim=0, radio=0, cs=1, display=0, dsc=0, band=0, msg22=0, assigned=0), radio_channel='A')[0])}"]  # class B: unsupported
    print("\n".join(out))


if __name__ == "__main__":
    main()
