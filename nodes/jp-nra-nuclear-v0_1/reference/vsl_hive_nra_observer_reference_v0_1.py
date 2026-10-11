import hashlib
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

SOURCE_HOME = "https://kinkyu.nra.go.jp/"
SOURCE_ID = "NRA_NUCLEAR_ALERT"
TERRITORY_ID = "JP"

BASE = "./runtime/jp-nra"
SOURCE_DIR = BASE + "/source"
FLOWER_PATH = SOURCE_DIR + "/flower.json"
OBSERVER_DIR = BASE + "/observer"
SEEN_PATH = OBSERVER_DIR + "/seen.json"

USER_AGENT = "VSL-HIVE-JP-NRA-Observer/0.1"
TIMEOUT_SECONDS = 15

NEGATIVE_MARKERS = (
    "訓練",
    "THIS IS AN EXERCISE",
    "異常なし",
    "特段の異常なし",
    "異常はありません",
    "異常はない",
    "影響なし",
)

# Deliberately conservative. Ambiguity means silence.
POSITIVE_MARKERS = (
    "原災法第10条",
    "原災法第１０条",
    "原災法第15条",
    "原災法第１５条",
    "施設敷地緊急事態",
    "全面緊急事態",
    "放射性物質の漏えい",
    "放射性物質漏えい",
    "異常を確認",
    "異常が確認",
    "影響あり",
)

# Current NRA article URLs observed on the official site:
# /kinkyu/YYYY/MM/post-N.html  (Emergency Information)
# /joho/YYYY/MM/post-N.html    (Information Notices)
#
# Archive indexes such as /kinkyu/index.html and /joho/index.html
# are deliberately excluded from LIVE event candidates.
INTERESTING_PATH = re.compile(
    r"^/(?:kinkyu|joho)/[0-9]{4}/[0-9]{2}/post-[0-9]+[.]html$"
)


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        self._href = dict(attrs).get("href")
        self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            text = " ".join(self._text).strip()
            self.links.append((self._href, text))
            self._href = None
            self._text = []


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


def fetch(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(
        req,
        timeout=TIMEOUT_SECONDS,
    ) as response:
        final_url = response.geturl()
        if not final_url.startswith(SOURCE_HOME):
            raise RuntimeError("SOURCE_REDIRECT_OUTSIDE_NRA")
        raw = response.read()
    return final_url, raw


def decode_html(raw):
    head = raw[:4096].decode("ascii", "ignore")
    match = re.search(
        r"""charset\s*=\s*["']?\s*([A-Za-z0-9._-]+)""",
        head,
        flags=re.I,
    )

    candidates = []
    if match:
        candidates.append(match.group(1))

    candidates.extend([
        "utf-8",
        "cp932",
        "shift_jis",
    ])

    seen = set()
    for encoding in candidates:
        key = encoding.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue

    return raw.decode("utf-8", "replace")


def visible_text(raw):
    text = decode_html(raw)
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def classify(text):
    upper = text.upper()

    if any(marker.upper() in upper for marker in NEGATIVE_MARKERS):
        return {
            "exercise": "訓練" in text or "THIS IS AN EXERCISE" in upper,
            "negative_status_detected": True,
            "positive_impact_confirmed": False,
            "publication_candidate": False,
            "reason": "EXCLUDED_OR_NEGATIVE",
        }

    positive = [
        marker
        for marker in POSITIVE_MARKERS
        if marker in text
    ]

    if not positive:
        return {
            "exercise": False,
            "negative_status_detected": False,
            "positive_impact_confirmed": False,
            "publication_candidate": False,
            "reason": "NO_EXPLICIT_POSITIVE_IMPACT",
        }

    return {
        "exercise": False,
        "negative_status_detected": False,
        "positive_impact_confirmed": True,
        "publication_candidate": True,
        "reason": "EXPLICIT_POSITIVE_IMPACT",
        "matched_markers": positive,
    }


def load_seen():
    try:
        with open(SEEN_PATH, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            return obj
    except FileNotFoundError:
        pass
    return {}


def save_seen(seen):
    os.makedirs(OBSERVER_DIR, exist_ok=True)
    tmp = SEEN_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    os.replace(tmp, SEEN_PATH)


def write_flower(entry_url, title, raw):
    os.makedirs(SOURCE_DIR, exist_ok=True)

    body = {
        "schema": "vsl.hive.jp-nra.local-flower.v0.1",
        "mode": "LIVE_OBSERVATION",
        "territory_id": TERRITORY_ID,
        "source": {
            "source_id": SOURCE_ID,
            "source_org": "Nuclear Regulation Authority of Japan",
            "source_url": SOURCE_HOME,
        },
        "provenance": {
            "source_raw_sha256": sha256_bytes(raw),
        },
        "observation": {
            "entry_id": entry_url,
            "title": title,
            "observed_at_ns": now_ns(),
        },
        "interpretation": {
            "exercise": False,
            "negative_status_detected": False,
            "positive_impact_confirmed": True,
            "publication_candidate": True,
        },
    }

    flower_sha256 = canonical_hash(body)
    flower = dict(body)
    flower["flower_sha256"] = flower_sha256

    tmp = FLOWER_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(flower, f, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    os.replace(tmp, FLOWER_PATH)

    return flower_sha256


def candidate_links(raw):
    parser = LinkParser()
    parser.feed(decode_html(raw))

    out = []
    for href, title in parser.links:
        absolute = urllib.parse.urljoin(SOURCE_HOME, href)
        parsed = urllib.parse.urlparse(absolute)

        if parsed.scheme != "https":
            continue

        if parsed.netloc != "kinkyu.nra.go.jp":
            continue

        if INTERESTING_PATH.match(parsed.path):
            out.append((absolute, title))

    # Preserve order while removing duplicates.
    dedup = []
    seen = set()
    for item in out:
        if item[0] in seen:
            continue
        seen.add(item[0])
        dedup.append(item)
    return dedup


def run_once():
    _, home_raw = fetch(SOURCE_HOME)
    seen = load_seen()

    candidates = candidate_links(home_raw)
    print("NRA_CANDIDATE_COUNT=" + str(len(candidates)), flush=True)

    for entry_url, anchor_title in candidates:
        _, raw = fetch(entry_url)
        source_sha = sha256_bytes(raw)

        if seen.get(entry_url) == source_sha:
            continue

        text = visible_text(raw)
        title = anchor_title.strip() or text[:240]
        decision = classify(title + " " + text)

        seen[entry_url] = source_sha
        save_seen(seen)

        if not decision["publication_candidate"]:
            print(
                "NRA_OBSERVER_SILENCE="
                + decision["reason"],
                flush=True,
            )
            continue

        flower_sha = write_flower(
            entry_url,
            title,
            raw,
        )

        print("NRA_POSITIVE_IMPACT=TRUE", flush=True)
        print("NRA_ENTRY_URL=" + entry_url, flush=True)
        print("FLOWER_SHA256=" + flower_sha, flush=True)
        return True

    print("NRA_OBSERVER_SILENCE=NO_NEW_POSITIVE_EVENT", flush=True)
    return False


if __name__ == "__main__":
    run_once()
