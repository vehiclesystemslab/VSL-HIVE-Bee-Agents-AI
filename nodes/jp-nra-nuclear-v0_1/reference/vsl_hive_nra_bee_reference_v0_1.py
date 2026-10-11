import ctypes
import hashlib
import json
import os
import re
import socket
import ssl
import struct
import time

BEE_ID = "JP-NRA-BEE-001"
TERRITORY_ID = "JP"
SOURCE_ID = "NRA_NUCLEAR_ALERT"

BASE = "./runtime/jp-nra"
SOURCE_DIR = BASE + "/source"
SOURCE_NAME = "flower.json"
SOURCE_PATH = SOURCE_DIR + "/" + SOURCE_NAME
STATE_DIR = BASE + "/bee"
STATE_PATH = STATE_DIR + "/bee_state.json"

CORE_HOST = "127.0.0.1"
CORE_PORT = 9710

GENESIS = "0" * 64
CORE_EVIDENCE_DIR = "./runtime/jp-nra-core/evidence"

EXPECTED_FLOWER_SCHEMA = "vsl.hive.jp-nra.local-flower.v0.1"

IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080
WATCH_MASK = IN_CLOSE_WRITE | IN_MOVED_TO

libc = ctypes.CDLL("libc.so.6", use_errno=True)
libc.inotify_init1.argtypes = [ctypes.c_int]
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


def recover_chain_tail():
    if not os.path.isdir(CORE_EVIDENCE_DIR):
        return 0, GENESIS

    packets = []
    for name in os.listdir(CORE_EVIDENCE_DIR):
        if not name.startswith("honey_") or not name.endswith(".json"):
            continue
        path = os.path.join(CORE_EVIDENCE_DIR, name)
        with open(path, "r", encoding="utf-8") as f:
            packet = json.load(f)
        packets.append((packet.get("event_seq"), name, packet))

    if not packets:
        return 0, GENESIS

    packets.sort(key=lambda item: (item[0], item[1]))

    expected_seq = 1
    previous_honey = GENESIS

    for seq, name, packet in packets:
        if not isinstance(seq, int) or seq != expected_seq:
            raise RuntimeError("RECOVERY_EVENT_SEQUENCE_INVALID")

        if packet.get("schema") != "vsl.hive.jp-nra.honey.v0.1":
            raise RuntimeError("RECOVERY_SCHEMA_INVALID")

        if packet.get("bee_id") != BEE_ID:
            raise RuntimeError("RECOVERY_BEE_ID_INVALID")

        if packet.get("territory_id") != TERRITORY_ID:
            raise RuntimeError("RECOVERY_TERRITORY_INVALID")

        if packet.get("source_id") != SOURCE_ID:
            raise RuntimeError("RECOVERY_SOURCE_INVALID")

        honey_sha = packet.get("honey_sha256")
        if not isinstance(honey_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", honey_sha):
            raise RuntimeError("RECOVERY_HONEY_SHA_INVALID")

        body = dict(packet)
        body.pop("honey_sha256", None)
        if honey_sha != canonical_hash(body):
            raise RuntimeError("RECOVERY_HONEY_HASH_MISMATCH")

        if packet.get("previous_honey_sha256") != previous_honey:
            raise RuntimeError("RECOVERY_CHAIN_LINK_INVALID")

        previous_honey = honey_sha
        expected_seq += 1

    return expected_seq - 1, previous_honey


def snapshot():
    with open(SOURCE_PATH, "rb") as f:
        raw = f.read()
    return raw, sha256_bytes(raw)


def write_state(state, event_seq, honey_sent, source_sha, last_honey_sha):
    os.makedirs(STATE_DIR, exist_ok=True)
    obj = {
        "schema": "vsl.hive.jp-nra.bee-state.v0.1",
        "bee_id": BEE_ID,
        "territory_id": TERRITORY_ID,
        "source_id": SOURCE_ID,
        "state": state,
        "event_seq": event_seq,
        "honey_sent": honey_sent,
        "source_slot_sha256": source_sha,
        "last_honey_sha256": last_honey_sha,
        "pid": os.getpid(),
    }
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, sort_keys=True)
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

    if stored != canonical_hash(body):
        raise RuntimeError("FLOWER_CANONICAL_HASH_MISMATCH")

    if d.get("schema") != EXPECTED_FLOWER_SCHEMA:
        raise RuntimeError("FLOWER_SCHEMA_MISMATCH")

    if d.get("mode") != "LIVE_OBSERVATION":
        raise RuntimeError("FLOWER_MODE_MISMATCH")

    if d.get("territory_id") != TERRITORY_ID:
        raise RuntimeError("FLOWER_TERRITORY_MISMATCH")

    source = d.get("source", {})
    if source.get("source_id") != SOURCE_ID:
        raise RuntimeError("FLOWER_SOURCE_MISMATCH")

    raw_sha = d.get("provenance", {}).get("source_raw_sha256")
    if not isinstance(raw_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", raw_sha):
        raise RuntimeError("SOURCE_RAW_SHA_INVALID")

    observation = d.get("observation", {})
    entry_id = observation.get("entry_id")
    if (
        not isinstance(entry_id, str)
        or not entry_id.startswith("https://kinkyu.nra.go.jp/")
    ):
        raise RuntimeError("ENTRY_ID_INVALID")

    title = observation.get("title")
    if not isinstance(title, str) or not title:
        raise RuntimeError("ENTRY_TITLE_INVALID")

    interpretation = d.get("interpretation", {})
    required = {
        "exercise": False,
        "negative_status_detected": False,
        "positive_impact_confirmed": True,
        "publication_candidate": True,
    }
    for key, expected in required.items():
        if interpretation.get(key) is not expected:
            raise RuntimeError("NRA_POLICY_INVALID_" + key.upper())

    return d, stored


def deposit(packet):
    ctx = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,
        cafile="./certs/nra/ca.crt",
    )
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.maximum_version = ssl.TLSVersion.TLSv1_3
    ctx.check_hostname = True
    ctx.load_cert_chain(
        certfile="./certs/nra/bee.crt",
        keyfile="./certs/nra/bee.key",
    )

    with socket.create_connection(
        (CORE_HOST, CORE_PORT),
        timeout=10,
    ) as raw:
        with ctx.wrap_socket(
            raw,
            server_hostname=CORE_HOST,
        ) as tls:
            cn = peer_cn(tls.getpeercert())

            if tls.version() != "TLSv1.3":
                raise RuntimeError("TLS_VERSION_MISMATCH")

            if cn != "HIVE-NRA-CORE-JP-02":
                raise RuntimeError("CORE_IDENTITY_MISMATCH")

            wire = (
                json.dumps(
                    packet,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
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

            if b"\n" not in buf:
                raise RuntimeError("ACK_LINE_INCOMPLETE")

            ack = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))

            if ack.get("ack") != "JP_NRA_ACK":
                raise RuntimeError("ACK_INVALID")

            if ack.get("event_seq") != packet["event_seq"]:
                raise RuntimeError("ACK_SEQUENCE_MISMATCH")

            if ack.get("honey_sha256") != packet["honey_sha256"]:
                raise RuntimeError("ACK_HONEY_MISMATCH")


os.makedirs(SOURCE_DIR, exist_ok=True)
if not os.path.exists(SOURCE_PATH):
    open(SOURCE_PATH, "ab").close()

raw, baseline_sha = snapshot()

event_seq, previous_honey = recover_chain_tail()
honey_sent = event_seq

write_state("SLEEP", event_seq, honey_sent, baseline_sha, previous_honey)
print("BEE_ID=" + BEE_ID, flush=True)
print("BEE_STATE=SLEEP", flush=True)
print("NRA_BEE_RECOVERED_EVENT_SEQ=" + str(event_seq), flush=True)
print("NRA_BEE_RECOVERED_PREVIOUS_HONEY=" + previous_honey, flush=True)

fd = libc.inotify_init1(0)
if fd < 0:
    err = ctypes.get_errno()
    raise OSError(err, os.strerror(err))

wd = libc.inotify_add_watch(
    fd,
    SOURCE_DIR.encode(),
    WATCH_MASK,
)
if wd < 0:
    err = ctypes.get_errno()
    raise OSError(err, os.strerror(err))

print("NRA_BEE_READY=PASS", flush=True)

while True:
    raw_events = os.read(fd, 4096)
    offset = 0

    while offset < len(raw_events):
        wd_ev, mask, cookie, name_len = struct.unpack_from(
            "iIII",
            raw_events,
            offset,
        )
        offset += struct.calcsize("iIII")

        name_raw = raw_events[offset:offset + name_len]
        offset += name_len

        name = name_raw.rstrip(b"\0").decode("utf-8", "replace")

        if name != SOURCE_NAME or not (mask & WATCH_MASK):
            continue

        event_seq += 1
        raw, source_sha = snapshot()

        write_state("WAKE", event_seq, honey_sent, source_sha, previous_honey)
        flower, flower_sha = validate_flower(raw)

        write_state("FORAGE", event_seq, honey_sent, source_sha, previous_honey)

        body = {
            "schema": "vsl.hive.jp-nra.honey.v0.1",
            "bee_id": BEE_ID,
            "territory_id": TERRITORY_ID,
            "source_id": SOURCE_ID,
            "event_seq": event_seq,
            "observed_at_ns": now_ns(),
            "flower_sha256": flower_sha,
            "source_raw_sha256": flower["provenance"]["source_raw_sha256"],
            "source_entry_id": flower["observation"]["entry_id"],
            "source_title": flower["observation"]["title"],
            "previous_honey_sha256": previous_honey,
        }

        honey_sha = canonical_hash(body)
        packet = dict(body)
        packet["honey_sha256"] = honey_sha

        write_state("DEPOSIT", event_seq, honey_sent, source_sha, previous_honey)
        deposit(packet)

        honey_sent += 1
        previous_honey = honey_sha

        write_state("SLEEP", event_seq, honey_sent, source_sha, previous_honey)

        print("NRA_HONEY_DEPOSIT=PASS", flush=True)
        print("EVENT_SEQ=" + str(event_seq), flush=True)
        print("HONEY_SHA256=" + honey_sha, flush=True)
        print("BEE_STATE=SLEEP", flush=True)
