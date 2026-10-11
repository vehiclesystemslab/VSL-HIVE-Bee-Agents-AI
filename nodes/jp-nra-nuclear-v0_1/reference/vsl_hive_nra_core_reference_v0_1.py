import hashlib
import json
import os
import re
import socket
import ssl
import time

HOST = "127.0.0.1"
PORT = 9710

EXPECTED_REMOTE_IP = "127.0.0.1"
EXPECTED_PEER_CN = "HIVE-NRA-BEE-JP-02"

EXPECTED_SCHEMA = "vsl.hive.jp-nra.honey.v0.1"
EXPECTED_BEE_ID = "JP-NRA-BEE-001"
EXPECTED_TERRITORY = "JP"
EXPECTED_SOURCE = "NRA_NUCLEAR_ALERT"

BASE = "./runtime/jp-nra-core"
EVIDENCE_DIR = BASE + "/evidence"
PUBLIC_DIR = BASE + "/public"
PUBLIC_EVENT_PATH = PUBLIC_DIR + "/public_event.json"

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


def persist_honey(packet):
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    name = (
        "honey_"
        + str(packet["event_seq"])
        + "_"
        + packet["honey_sha256"]
        + ".json"
    )
    path = EVIDENCE_DIR + "/" + name
    tmp = path + ".tmp"

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(packet, f, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)
    return path


def publish_public_event(packet):
    os.makedirs(PUBLIC_DIR, exist_ok=True)

    event = {
        "schema": "vsl.hive.jp-nra.public-event.v0.1",
        "public_event": True,
        "territory_id": packet["territory_id"],
        "source_id": packet["source_id"],
        "source_org": "Nuclear Regulation Authority of Japan",
        "source_entry_id": packet["source_entry_id"],
        "source_title": packet["source_title"],
        "observed_at_ns": packet["observed_at_ns"],
        "evidence_id": packet["honey_sha256"],
        "generated_at_ns": time.time_ns(),
    }

    tmp = PUBLIC_EVENT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(event, f, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    os.replace(tmp, PUBLIC_EVENT_PATH)


os.makedirs(BASE, exist_ok=True)

ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
ctx.minimum_version = ssl.TLSVersion.TLSv1_3
ctx.maximum_version = ssl.TLSVersion.TLSv1_3
ctx.verify_mode = ssl.CERT_REQUIRED
ctx.load_cert_chain(
    certfile="./certs/nra/core.crt",
    keyfile="./certs/nra/core.key",
)
ctx.load_verify_locations(
    cafile="./certs/nra/ca.crt",
)

listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind((HOST, PORT))
listener.listen(4)

print("NRA_CORE_STATE=READY", flush=True)

previous_honey = GENESIS

while True:
    raw, addr = listener.accept()
    remote_ip = addr[0]

    with ctx.wrap_socket(raw, server_side=True) as tls:
        cert = tls.getpeercert()
        cn = peer_cn(cert)

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

        if honey_sha != canonical_hash(body):
            raise RuntimeError("HONEY_HASH_MISMATCH")

        checks = {
            "SCHEMA": packet.get("schema") == EXPECTED_SCHEMA,
            "BEE_ID": packet.get("bee_id") == EXPECTED_BEE_ID,
            "TERRITORY": packet.get("territory_id") == EXPECTED_TERRITORY,
            "SOURCE": packet.get("source_id") == EXPECTED_SOURCE,
            "EVENT_SEQ": isinstance(packet.get("event_seq"), int)
                         and packet.get("event_seq") >= 1,
            "PREVIOUS_HONEY":
                packet.get("previous_honey_sha256") == previous_honey,
            "FLOWER_SHA":
                isinstance(packet.get("flower_sha256"), str)
                and re.fullmatch(
                    r"[0-9a-f]{64}",
                    packet.get("flower_sha256"),
                ) is not None,
            "SOURCE_RAW_SHA":
                isinstance(packet.get("source_raw_sha256"), str)
                and re.fullmatch(
                    r"[0-9a-f]{64}",
                    packet.get("source_raw_sha256"),
                ) is not None,
            "SOURCE_ENTRY_ID":
                isinstance(packet.get("source_entry_id"), str)
                and packet.get("source_entry_id").startswith(
                    "https://kinkyu.nra.go.jp/"
                ),
            "SOURCE_TITLE":
                isinstance(packet.get("source_title"), str)
                and bool(packet.get("source_title")),
        }

        for name, ok in checks.items():
            if not ok:
                raise RuntimeError("VALIDATION_FAILED_" + name)

        evidence_path = persist_honey(packet)
        publish_public_event(packet)
        previous_honey = honey_sha

        ack = {
            "ack": "JP_NRA_ACK",
            "event_seq": packet["event_seq"],
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

        print("NRA_HONEY_INTEGRITY=PASS", flush=True)
        print("EVIDENCE_PATH=" + evidence_path, flush=True)
        print("PUBLIC_EVENT_WRITTEN=TRUE", flush=True)
