import re
import hashlib
import json
import socket
import ssl

HOST = "127.0.0.1"
PORT = 9700

EXPECTED_REMOTE_IP = "127.0.0.1"
EXPECTED_PEER_CN = "HIVE-BEE-PUBLIC"

EXPECTED_SCHEMA = "vsl.hive.aimtg.honey.v0.1"
EXPECTED_EXPERIMENT = "EXP-011/G07"
EXPECTED_BEE_ID = "JP-ALPHA-BEE-003"
EXPECTED_TERRITORY = "JP"
EXPECTED_SOURCE = "JMA_EQVOL"




GENESIS = "0" * 64


def canonical_hash(body):
    raw = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(raw).hexdigest()


def peer_cn(cert):
    for rdn in cert.get("subject", ()):
        for key, value in rdn:
            if key == "commonName":
                return value
    return ""


ctx = ssl.create_default_context(
    ssl.Purpose.CLIENT_AUTH
)

ctx.minimum_version = ssl.TLSVersion.TLSv1_3
ctx.maximum_version = ssl.TLSVersion.TLSv1_3

ctx.verify_mode = ssl.CERT_REQUIRED

ctx.load_cert_chain(
    certfile="./certs/core.crt",
    keyfile="./certs/core.key",
)

ctx.load_verify_locations(
    cafile="./certs/ca.crt",
)

listener = socket.socket(
    socket.AF_INET,
    socket.SOCK_STREAM,
)

listener.setsockopt(
    socket.SOL_SOCKET,
    socket.SO_REUSEADDR,
    1,
)

listener.bind((HOST, PORT))
listener.listen(4)

print("EXPERIMENT=EXP-011/G07", flush=True)
print("CORE_HOST=" + HOST, flush=True)
print("CORE_PORT=" + str(PORT), flush=True)
print("TLS_MIN=TLSv1.3", flush=True)
print("EXPECTED_CONNECTIONS=1", flush=True)
print("RECEIVED_CONNECTION_COUNT=0", flush=True)
print("CORE_STATE=AWAITING_1_JP_HONEY", flush=True)
print("SERVER_READY=PASS", flush=True)

raw, addr = listener.accept()

remote_ip = addr[0]

with ctx.wrap_socket(
    raw,
    server_side=True,
) as tls:

    cert = tls.getpeercert()
    cn = peer_cn(cert)

    print("CONNECTION_1_REMOTE_IP=" + remote_ip, flush=True)
    print("CONNECTION_1_TLS_VERSION=" + str(tls.version()), flush=True)
    print("CONNECTION_1_PEER_CN=" + cn, flush=True)

    if remote_ip != EXPECTED_REMOTE_IP:
        raise RuntimeError("REMOTE_IP_MISMATCH")

    if tls.version() != "TLSv1.3":
        raise RuntimeError("TLS_VERSION_MISMATCH")

    if cn != EXPECTED_PEER_CN:
        raise RuntimeError("PEER_CN_MISMATCH")

    buf = b""

    while b"\n" not in buf:
        chunk = tls.recv(4096)

        if not chunk:
            break

        buf += chunk

    if b"\n" not in buf:
        raise RuntimeError("PACKET_LINE_INCOMPLETE")

    packet = json.loads(
        buf.split(b"\n", 1)[0].decode("utf-8")
    )

    honey_sha = packet.get("honey_sha256")

    body = dict(packet)
    body.pop("honey_sha256", None)

    calculated = canonical_hash(body)

    if honey_sha != calculated:
        raise RuntimeError("HONEY_HASH_MISMATCH")

    checks = {
        "SCHEMA":
            packet.get("schema") == EXPECTED_SCHEMA,

        "EXPERIMENT":
            packet.get("experiment") == EXPECTED_EXPERIMENT,

        "BEE_ID":
            packet.get("bee_id") == EXPECTED_BEE_ID,

        "TERRITORY":
            packet.get("territory_id") == EXPECTED_TERRITORY,

        "SOURCE":
            packet.get("source_id") == EXPECTED_SOURCE,

        "EVENT_SEQ":
            packet.get("event_seq") == 1,

        "PREVIOUS_HONEY":
            packet.get("previous_honey_sha256") == GENESIS,

        "FLOWER_SHA":
            isinstance(
                packet.get("flower_sha256"),
                str,
            )
            and re.fullmatch(
                r"[0-9a-f]{64}",
                packet.get("flower_sha256"),
            )
            is not None,

        "SOURCE_RAW_SHA":
            isinstance(
                packet.get("source_raw_sha256"),
                str,
            )
            and re.fullmatch(
                r"[0-9a-f]{64}",
                packet.get("source_raw_sha256"),
            )
            is not None,

        "SOURCE_ENTRY_ID":
            isinstance(
                packet.get("source_entry_id"),
                str,
            )
            and packet.get(
                "source_entry_id"
            ).startswith(
                "https://www.data.jma.go.jp/"
                "developer/xml/data/"
            )
            and packet.get(
                "source_entry_id"
            ).endswith(".xml"),

        "SOURCE_ENTRY_UPDATED":
            isinstance(
                packet.get("source_entry_updated"),
                str,
            )
            and bool(
                packet.get("source_entry_updated")
            ),
    }

    for name, ok in checks.items():
        print(
            "CONNECTION_1_" + name + "="
            + ("PASS" if ok else "FAIL"),
            flush=True,
        )

        if not ok:
            raise RuntimeError(
                "VALIDATION_FAILED_" + name
            )

    print(
        "CONNECTION_1_HONEY_SHA256="
        + honey_sha,
        flush=True,
    )

    print(
        "CONNECTION_1_HONEY_INTEGRITY=PASS",
        flush=True,
    )

    ack = {
        "ack": "EXP011_G07_ACK",
        "event_seq": 1,
        "honey_sha256": honey_sha,
    }

    tls.sendall(
        (
            json.dumps(
                ack,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    )

    print("CONNECTION_1_ACK_SENT=PASS", flush=True)

listener.close()

print("FINAL_RECEIVED_CONNECTION_COUNT=1", flush=True)
print("G07_CORE_RECEIVER=PASS", flush=True)
