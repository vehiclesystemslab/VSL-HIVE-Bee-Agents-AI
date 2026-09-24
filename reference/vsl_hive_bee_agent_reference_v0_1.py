import re
import ctypes
import hashlib
import json
import os
import socket
import ssl
import struct
import time

BEE_ID = "JP-ALPHA-BEE-003"
TERRITORY_ID = "JP"

SOURCE_ID = "JMA_EQVOL"

EXPERIMENT_RUNTIME = "EXP-011/G07"
EXPERIMENT_HONEY = "EXP-011/G07"

BASE = "./runtime/jp-bee"

SOURCE_DIR = BASE + "/source"
SOURCE_NAME = "flower.json"
SOURCE_PATH = SOURCE_DIR + "/" + SOURCE_NAME

RUNTIME_DIR = BASE + "/runtime"
STATE_PATH = RUNTIME_DIR + "/bee_state.json"

CORE_HOST = "127.0.0.1"
CORE_PORT = 9700

GENESIS = "0" * 64
MAX_EVENTS = 1

EXPECTED_FLOWER_SCHEMA = (
    "vsl.hive.aimtg.local-flower.v0.1"
)




IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080

WATCH_MASK = IN_CLOSE_WRITE | IN_MOVED_TO

libc = ctypes.CDLL(
    "libc.so.6",
    use_errno=True,
)

libc.inotify_init1.argtypes = [
    ctypes.c_int
]

libc.inotify_init1.restype = ctypes.c_int

libc.inotify_add_watch.argtypes = [
    ctypes.c_int,
    ctypes.c_char_p,
    ctypes.c_uint32,
]

libc.inotify_add_watch.restype = ctypes.c_int


def now_ns():
    return time.time_ns()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def canonical_hash(obj):
    raw = json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return sha256_bytes(raw)


def snapshot():
    with open(SOURCE_PATH, "rb") as f:
        raw = f.read()

    return raw, sha256_bytes(raw)


def write_state(
    state,
    event_seq,
    honey_sent,
    source_sha,
    last_honey_sha,
):
    obj = {
        "schema":
            "vsl.hive.aimtg.bee-state.v0.1",

        "experiment":
            EXPERIMENT_RUNTIME,

        "bee_id":
            BEE_ID,

        "territory_id":
            TERRITORY_ID,

        "source_id":
            SOURCE_ID,

        "state":
            state,

        "event_seq":
            event_seq,

        "honey_sent":
            honey_sent,

        "source_slot_sha256":
            source_sha,

        "last_honey_sha256":
            last_honey_sha,

        "pid":
            os.getpid(),
    }

    tmp = STATE_PATH + ".tmp"

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(
            obj,
            f,
            sort_keys=True,
        )
        f.write("\n")

    os.replace(tmp, STATE_PATH)


def peer_cn(cert):
    for rdn in cert.get("subject", ()):
        for key, value in rdn:
            if key == "commonName":
                return value
    return ""


def validate_flower(raw):
    d = json.loads(raw.decode("utf-8"))

    stored = d.get("flower_sha256")

    body = dict(d)
    body.pop("flower_sha256", None)

    calculated = canonical_hash(body)

    if stored != calculated:
        raise RuntimeError(
            "FLOWER_CANONICAL_HASH_MISMATCH"
        )

    if d.get("schema") != EXPECTED_FLOWER_SCHEMA:
        raise RuntimeError(
            "FLOWER_SCHEMA_MISMATCH"
        )

    if d.get("mode") != "LIVE_OBSERVATION":
        raise RuntimeError(
            "FLOWER_MODE_MISMATCH"
        )

    if d.get("territory_id") != TERRITORY_ID:
        raise RuntimeError(
            "FLOWER_TERRITORY_MISMATCH"
        )

    if (
        d.get("source", {}).get("source_id")
        != SOURCE_ID
    ):
        raise RuntimeError(
            "FLOWER_SOURCE_MISMATCH"
        )

    raw_sha = (
        d.get("provenance", {}).get(
            "source_raw_sha256"
        )
    )

    if not (
        isinstance(raw_sha, str)
        and re.fullmatch(
            r"[0-9a-f]{64}",
            raw_sha,
        )
    ):
        raise RuntimeError(
            "SOURCE_RAW_SHA_INVALID"
        )

    entry_id = (
        d.get("observation", {}).get(
            "entry_id"
        )
    )

    if not (
        isinstance(entry_id, str)
        and entry_id.startswith(
            "https://www.data.jma.go.jp/"
            "developer/xml/data/"
        )
        and entry_id.endswith(".xml")
    ):
        raise RuntimeError(
            "ENTRY_ID_INVALID"
        )

    updated = (
        d.get("observation", {}).get(
            "updated"
        )
    )

    if not (
        isinstance(updated, str)
        and updated
    ):
        raise RuntimeError(
            "ENTRY_UPDATED_INVALID"
        )

    if (
        d.get("interpretation", {}).get(
            "anomaly_declared"
        )
        is not False
    ):
        raise RuntimeError(
            "ANOMALY_FLAG_INVALID"
        )

    if (
        d.get("interpretation", {}).get(
            "public_box_publish"
        )
        is not False
    ):
        raise RuntimeError(
            "PUBLIC_BOX_FLAG_INVALID"
        )

    return d, stored



def deposit(packet):
    ctx = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,
        cafile="./certs/ca.crt",
    )

    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.maximum_version = ssl.TLSVersion.TLSv1_3

    ctx.check_hostname = True

    ctx.load_cert_chain(
        certfile="./certs/bee.crt",
        keyfile="./certs/bee.key",
    )

    with socket.create_connection(
        (CORE_HOST, CORE_PORT),
        timeout=10,
    ) as raw:

        with ctx.wrap_socket(
            raw,
            server_hostname=CORE_HOST,
        ) as tls:

            cn = peer_cn(
                tls.getpeercert()
            )

            print(
                "DEPOSIT_TLS_VERSION="
                + str(tls.version()),
                flush=True,
            )

            print(
                "DEPOSIT_PEER_CN="
                + cn,
                flush=True,
            )

            if tls.version() != "TLSv1.3":
                raise RuntimeError(
                    "TLS_VERSION_MISMATCH"
                )

            if cn != "HIVE-CORE-PUBLIC":
                raise RuntimeError(
                    "CORE_IDENTITY_MISMATCH"
                )

            wire = (
                json.dumps(
                    packet,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")

            tls.sendall(wire)

            buf = b""

            while b"\n" not in buf:
                chunk = tls.recv(4096)

                if not chunk:
                    break

                buf += chunk

            ack = json.loads(
                buf.split(
                    b"\n",
                    1,
                )[0].decode("utf-8")
            )

            if ack.get("ack") != "EXP011_G07_ACK":
                raise RuntimeError(
                    "ACK_INVALID"
                )

            if ack.get("event_seq") != 1:
                raise RuntimeError(
                    "ACK_SEQUENCE_MISMATCH"
                )

            if (
                ack.get("honey_sha256")
                != packet["honey_sha256"]
            ):
                raise RuntimeError(
                    "ACK_HONEY_MISMATCH"
                )

            print(
                "DEPOSIT_ACK=PASS",
                flush=True,
            )


raw, baseline_sha = snapshot()

event_seq = 0
honey_sent = 0
previous_honey = GENESIS

write_state(
    "SLEEP",
    event_seq,
    honey_sent,
    baseline_sha,
    previous_honey,
)

print("EXPERIMENT=" + EXPERIMENT_RUNTIME, flush=True)
print("BEE_ID=" + BEE_ID, flush=True)
print("BEE_PID=" + str(os.getpid()), flush=True)
print("TERRITORY_ID=" + TERRITORY_ID, flush=True)
print("SOURCE_ID=" + SOURCE_ID, flush=True)
print("WATCH_MODE=INOTIFY_BLOCKING", flush=True)
print("MAX_EVENTS=1", flush=True)
print("BASELINE_SLOT_SHA256=" + baseline_sha, flush=True)
print("HONEY_CHAIN_GENESIS=" + GENESIS, flush=True)
print("BEE_STATE=SLEEP", flush=True)
print("EVENT_SEQ=0", flush=True)
print("HONEY_SENT=0", flush=True)

fd = libc.inotify_init1(0)

if fd < 0:
    err = ctypes.get_errno()
    raise OSError(
        err,
        os.strerror(err),
    )

wd = libc.inotify_add_watch(
    fd,
    SOURCE_DIR.encode(),
    WATCH_MASK,
)

if wd < 0:
    err = ctypes.get_errno()
    raise OSError(
        err,
        os.strerror(err),
    )

print("INOTIFY_WATCH=PASS", flush=True)
print("G07_JP_BEE_READY=PASS", flush=True)

while True:

    raw_events = os.read(fd, 4096)

    offset = 0

    while offset < len(raw_events):

        wd_ev, mask, cookie, name_len = (
            struct.unpack_from(
                "iIII",
                raw_events,
                offset,
            )
        )

        offset += struct.calcsize("iIII")

        name_raw = raw_events[
            offset:offset + name_len
        ]

        offset += name_len

        name = name_raw.rstrip(
            b"\0"
        ).decode(
            "utf-8",
            "replace",
        )

        if name != SOURCE_NAME:
            continue

        if not (mask & WATCH_MASK):
            continue

        if event_seq >= MAX_EVENTS:
            print(
                "EXTRA_FLOWER_EVENT_IGNORED=TRUE",
                flush=True,
            )
            continue

        event_seq += 1

        print(
            "FLOWER_EVENT=1",
            flush=True,
        )

        print(
            "STATE_TRANSITION=SLEEP->WAKE",
            flush=True,
        )

        raw, source_sha = snapshot()

        write_state(
            "WAKE",
            event_seq,
            honey_sent,
            source_sha,
            previous_honey,
        )

        print(
            "BEE_STATE=WAKE",
            flush=True,
        )

        flower, flower_sha = (
            validate_flower(raw)
        )

        print(
            "FLOWER_VALIDATION=PASS",
            flush=True,
        )

        print(
            "FLOWER_SHA256="
            + flower_sha,
            flush=True,
        )

        print(
            "STATE_TRANSITION=WAKE->FORAGE",
            flush=True,
        )

        write_state(
            "FORAGE",
            event_seq,
            honey_sent,
            source_sha,
            previous_honey,
        )

        print(
            "BEE_STATE=FORAGE",
            flush=True,
        )

        body = {
            "schema":
                "vsl.hive.aimtg.honey.v0.1",

            "experiment":
                EXPERIMENT_HONEY,

            "bee_id":
                BEE_ID,

            "territory_id":
                TERRITORY_ID,

            "source_id":
                SOURCE_ID,

            "event_seq":
                event_seq,

            "observed_at_ns":
                now_ns(),

            "flower_sha256":
                flower_sha,

            "source_raw_sha256":
                flower["provenance"][
                    "source_raw_sha256"
                ],

            "source_entry_id":
                flower["observation"][
                    "entry_id"
                ],

            "source_entry_updated":
                flower["observation"][
                    "updated"
                ],

            "previous_honey_sha256":
                previous_honey,
        }

        honey_sha = canonical_hash(body)

        packet = dict(body)
        packet["honey_sha256"] = honey_sha

        print(
            "STATE_TRANSITION=FORAGE->DEPOSIT",
            flush=True,
        )

        write_state(
            "DEPOSIT",
            event_seq,
            honey_sent,
            source_sha,
            previous_honey,
        )

        print(
            "BEE_STATE=DEPOSIT",
            flush=True,
        )

        print(
            "PREVIOUS_HONEY_SHA256="
            + previous_honey,
            flush=True,
        )

        print(
            "HONEY_SHA256="
            + honey_sha,
            flush=True,
        )

        deposit(packet)

        honey_sent += 1
        previous_honey = honey_sha

        write_state(
            "SLEEP",
            event_seq,
            honey_sent,
            source_sha,
            previous_honey,
        )

        print(
            "STATE_TRANSITION=DEPOSIT->SLEEP",
            flush=True,
        )

        print(
            "BEE_STATE=SLEEP",
            flush=True,
        )

        print(
            "EVENT_SEQ=1",
            flush=True,
        )

        print(
            "HONEY_SENT=1",
            flush=True,
        )

        print(
            "LAST_HONEY_SHA256="
            + previous_honey,
            flush=True,
        )

        print(
            "G07_ONE_LIVE_CYCLE_COMPLETE=PASS",
            flush=True,
        )
